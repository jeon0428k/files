import sys
import yaml
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
from collections import OrderedDict

CONFIG_FILE = "./config/config.yml"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, msg: str):
        for s in self.streams:
            s.write(msg)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def _clean_rel_path(s: str) -> str:
    return str(s).strip().strip("/").strip("\\")


def to_posix(s: str) -> str:
    return s.replace("\\", "/")


def fail_exit(msg: str, code: int = 2) -> None:
    print(msg)
    sys.exit(code)


def resolve_worklist_path(raw: str) -> Path:
    s = raw.strip()
    p = Path(s).expanduser()

    if not p.is_absolute():
        fail_exit(f"[WORKLIST-FAIL] relative path is not allowed: {raw}")

    if not p.exists():
        fail_exit(f"[WORKLIST-FAIL] path not found: {p}")

    return p.resolve()


def read_worklist(worklist_file: str) -> tuple[list[Path], dict[Path, list[str]]]:
    p = Path(worklist_file)
    if not p.exists():
        print(f"> {now_str()}")
        fail_exit(f"worklist file not found: {p.resolve()}")

    items: list[Path] = []
    orin_map: dict[Path, list[str]] = {}

    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue

        abs_path = resolve_worklist_path(s)
        items.append(abs_path)
        orin_map.setdefault(abs_path, []).append(s)

    return items, orin_map


def normalize_svr_path_pairs(raw_svr_path) -> list[tuple[str, str]]:
    if raw_svr_path is None:
        return []

    if isinstance(raw_svr_path, str):
        raw_svr_path = [raw_svr_path]

    if not isinstance(raw_svr_path, list):
        return []

    out: list[tuple[str, str]] = []
    for item in raw_svr_path:
        if isinstance(item, str):
            p = item.strip()
            if p:
                out.append(("", p))
            continue

        if isinstance(item, (list, tuple)) and len(item) == 2:
            prefix = "" if item[0] is None else str(item[0]).strip()
            path = "" if item[1] is None else str(item[1]).strip()
            if path:
                out.append((prefix, path))
            continue

    return out


def build_repo_base_map(repositories: list[dict]) -> dict[str, dict]:
    repo_base_map: dict[str, dict] = {}
    for r in repositories:
        name = r["name"]
        root = Path(r["root"]).resolve()
        base = (root / r["path"]).resolve()

        raw_svr_path = r.get("svr_path", None)
        if raw_svr_path is None:
            legacy_dir = r.get("dir", "")
            raw_svr_path = [legacy_dir] if legacy_dir else []

        svr_path_pairs = normalize_svr_path_pairs(raw_svr_path)

        repo_base_map[name] = {
            "name": name,
            "root": root,
            "base": base,
            "svr_path": svr_path_pairs,
            "execute": bool(r.get("execute", False)),
            "trans_path": r.get("trans_path", []) or [],
            "trans_file": r.get("trans_file", []) or [],
            "build_file": r.get("build_file"),
            "src_path": "" if r.get("src_path") is None else str(r.get("src_path")).strip(),
        }
    return repo_base_map


def find_repo_name_by_root(src_abs: Path, repo_base_map: dict[str, dict]) -> Optional[str]:
    for name, info in repo_base_map.items():
        root = info["root"]
        try:
            src_abs.relative_to(root)
            return name
        except Exception:
            pass
    return None


def apply_transform_one(src_abs: Path, repo_base_map: dict[str, dict]) -> tuple[Path, Optional[str]]:
    repo_name = find_repo_name_by_root(src_abs, repo_base_map)
    if not repo_name:
        return src_abs, None

    info = repo_base_map[repo_name]
    repo_root: Path = info["root"]
    base_out: Path = info["base"]
    trans_path = info["trans_path"]
    trans_file = info["trans_file"]

    rel_kind = ""
    rel_posix = ""

    try:
        rel_posix = to_posix(str(src_abs.relative_to(base_out)))
        rel_kind = "base"
    except Exception:
        try:
            rel_posix = to_posix(str(src_abs.relative_to(repo_root)))
            rel_kind = "root"
        except Exception:
            return src_abs, repo_name

    new_rel = rel_posix

    trans_path_matched = False
    for src_prefix, dst_prefix in trans_path:
        sp = to_posix(src_prefix).strip("/")
        dp = to_posix(dst_prefix).strip("/")

        if sp and (new_rel == sp or new_rel.startswith(sp + "/")):
            rest = new_rel[len(sp):]
            if rest.startswith("/"):
                rest = rest[1:]

            if dp:
                new_rel = dp + ("/" + rest if rest else "")
            else:
                new_rel = rest

            trans_path_matched = True
            break

    for src_ext, dst_ext in trans_file:
        if new_rel.endswith(src_ext):
            new_rel = new_rel[:-len(src_ext)] + dst_ext
            break

    if rel_kind == "base":
        out_path = base_out.joinpath(*new_rel.split("/")) if new_rel else base_out
        return out_path, repo_name

    if trans_path_matched:
        out_path = base_out.joinpath(*new_rel.split("/")) if new_rel else base_out
        return out_path, repo_name

    out_path = repo_root.joinpath(*new_rel.split("/")) if new_rel else repo_root
    return out_path, repo_name


def apply_transforms_grouped(inputs: list[Path], repo_base_map: dict[str, dict]) -> dict[Path, list[Path]]:
    grouped: dict[Path, list[Path]] = {}
    for src_abs in inputs:
        changed, _ = apply_transform_one(src_abs, repo_base_map)
        grouped.setdefault(changed, []).append(src_abs)

    for k in list(grouped.keys()):
        grouped[k] = sorted(grouped[k], key=lambda x: str(x))

    return grouped


def classify_grouped(
    grouped: dict[Path, list[Path]],
    repo_base_map: dict[str, dict],
) -> tuple[dict[str, dict[Path, list[Path]]], dict[Path, list[Path]]]:
    repo_grouped: dict[str, dict[Path, list[Path]]] = {}
    unmapped: dict[Path, list[Path]] = {}

    for changed, src_list in grouped.items():
        mapped = False
        for repo_name, info in repo_base_map.items():
            base: Path = info["base"]
            try:
                changed.relative_to(base)
                repo_grouped.setdefault(repo_name, {})[changed] = src_list
                mapped = True
                break
            except Exception:
                pass

        if not mapped:
            unmapped[changed] = src_list

    return repo_grouped, unmapped


def ensure_empty_dir(p: Path) -> None:
    if p.exists():
        print(f"[REMOVE] {p}")
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def normalize_copy_roots(svr_path_pairs: list[tuple[str, str]], repo_root: Path) -> list[Path]:
    if not svr_path_pairs:
        repo_root.mkdir(parents=True, exist_ok=True)
        return [repo_root]

    roots: list[Path] = []
    for _, p in svr_path_pairs:
        p2 = _clean_rel_path(p)
        root = (repo_root / p2) if p2 else repo_root
        root.mkdir(parents=True, exist_ok=True)
        roots.append(root)

    return roots


def copy_grouped_and_log_multi(
    base_path: Path,
    target_roots: list[Path],
    grouped: dict[Path, list[Path]],
) -> list[tuple[str, Path, list[Path], list[Path]]]:
    logs: list[tuple[str, Path, list[Path], list[Path]]] = []

    for changed, src_list in grouped.items():
        if not changed.exists():
            logs.append(("X", changed, [], src_list))
            continue

        try:
            rel = changed.relative_to(base_path)
        except Exception:
            logs.append(("X", changed, [], src_list))
            continue

        copied_list: list[Path] = []
        for root in target_roots:
            try:
                copied = root / rel
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(changed, copied)
                copied_list.append(copied)
            except Exception:
                pass

        logs.append(("O" if copied_list else "X", changed, copied_list, src_list))

    return sorted(logs, key=lambda x: (0 if x[0] == "O" else 1, str(x[1])))


def format_orin_block(src_list: list[Path], orin_map: dict[Path, list[str]]) -> str:
    idx_map: dict[Path, int] = {}
    flat: list[str] = []

    for p in src_list:
        originals = orin_map.get(p)
        i = idx_map.get(p, 0)

        if originals and i < len(originals):
            flat.append(originals[i])
            idx_map[p] = i + 1
        else:
            flat.append(str(p))

    total_cnt = len(flat)
    counter = OrderedDict()
    for s in flat:
        counter[s] = counter.get(s, 0) + 1

    out: list[str] = []
    for path, cnt in counter.items():
        out.append(f"({cnt}){path}")

    return f"({total_cnt})[{', '.join(out)}]"


def format_copy_block(paths: list[Path]) -> str:
    if not paths:
        return ""
    if len(paths) == 1:
        return str(paths[0])
    return f"({len(paths)})[{', '.join(str(p) for p in paths)}]"


def print_unmapped(unmapped: dict[Path, list[Path]], is_orin_log: bool, orin_map: dict[Path, list[str]]) -> None:
    if not unmapped:
        return
    print("==================================================================")
    print("[UNMAPPED]")
    print("-------")
    for changed in sorted(unmapped.keys(), key=lambda x: str(x)):
        src_list = unmapped[changed]
        print(f"[X] {changed}")
        if is_orin_log:
            print(f"    {format_orin_block(src_list, orin_map)}")
    print("==================================================================")


def count_grouped(grouped: dict[Path, list[Path]]) -> tuple[int, int]:
    return len(grouped), sum(len(v) for v in grouped.values())


def add_counts(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def build_prefix_by_label(svr_path_pairs: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for prefix, p in svr_path_pairs:
        p2 = _clean_rel_path(p)
        if not p2:
            continue
        label = p2.split("/")[0].split("\\")[0]
        if label and label not in out:
            out[label] = "" if prefix is None else str(prefix).strip()
    return out


def add_success_copied_by_label(
    success_by_label: dict[str, list[str]],
    repo_root: Path,
    copied_list: list[Path],
    prefix_by_label: dict[str, str],
) -> None:
    for copied in copied_list:
        try:
            rel = copied.relative_to(repo_root)
        except Exception:
            continue

        parts = rel.parts
        if not parts:
            continue

        label = parts[0]
        rest_parts = parts[1:]
        rest = "/" + "/".join(rest_parts) if rest_parts else "/"

        prefix = prefix_by_label.get(label, "")
        if prefix:
            rest = prefix.rstrip("/") + rest

        success_by_label.setdefault(label, []).append(rest)


def print_success_by_label(success_by_label: dict[str, list[str]]) -> None:
    if not success_by_label:
        return

    for label in sorted(success_by_label.keys()):
        items = sorted(set(success_by_label[label]))
        print("==================================================================")
        print(f"[{label}]")
        print("------------------------------------------------------------------")
        for p in items:
            print(p)
        print("==================================================================")
        print()


def run_ant_build_one(ant_cmd: str, build_file: str, base_path: str) -> None:
    ant = Path(str(ant_cmd)).expanduser()
    if not ant.exists():
        fail_exit(f"ant_cmd not found: {ant}")

    bf = Path(str(build_file)).expanduser()
    if not bf.exists():
        print("------------------------------------------------------------------")
        print(f"[BUILD]")
        print("-------")
        print(f"build_file not found: {bf}")
        print("==================================================================")
        sys.exit(2)

    print("------------------------------------------------------------------")
    print(f"[BUILD]")
    print("-------")
    print(f"Path: {base_path}")
    print(f"Antfile: {ant}")

    cmd = ["cmd", "/c", str(ant), "-f", str(bf)]

    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception as e:
        print(f"[BUILD-FAIL] exec error: {e}")
        print("==================================================================")
        sys.exit(2)

    if r.stdout:
        print(r.stdout.rstrip())

    if r.returncode != 0:
        print(f"[BUILD-FAIL] returncode={r.returncode}")
        print("==================================================================")
        sys.exit(2)

    print("[BUILD-OK]")
    print("------------------------------------------------------------------")


def copy_worklist_files_to_repo_src(
    repo_src_root: Path,
    repo_out_root: Path,
    src_path: str,
    worklist_inputs: list[Path],
) -> tuple[int, int, list[Path]]:
    sp = _clean_rel_path(src_path)
    dest_base = repo_out_root / sp if sp else repo_out_root

    copied = 0
    skipped = 0
    copied_files: list[Path] = []

    seen: set[Path] = set()
    for src_abs in worklist_inputs:
        if src_abs in seen:
            continue
        seen.add(src_abs)

        try:
            rel = src_abs.relative_to(repo_src_root)
        except Exception:
            continue

        if not src_abs.exists() or not src_abs.is_file():
            skipped += 1
            continue

        dst = dest_base / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_abs, dst)
            copied += 1
            copied_files.append(dst)
        except Exception:
            skipped += 1

    return copied, skipped, copied_files


def run_pipeline(config: dict) -> None:
    print(f"> {now_str()}\n")

    copy_root = Path(config["copy_dir"])
    worklist_file = config.get("worklist_file")
    if not worklist_file:
        fail_exit("worklist_file is required")

    ant_cmd = config.get("ant_cmd")
    if not ant_cmd:
        fail_exit("ant_cmd is required")

    repositories = config.get("repositories", []) or []
    if not repositories:
        fail_exit("repositories is empty")

    is_orin_log = bool(config.get("is_orin_log", True))

    repo_base_map = build_repo_base_map(repositories)

    raw_inputs, orin_map = read_worklist(worklist_file)
    grouped_all = apply_transforms_grouped(raw_inputs, repo_base_map)
    repo_grouped, unmapped = classify_grouped(grouped_all, repo_base_map)

    total_all = (len(grouped_all), sum(len(v) for v in grouped_all.values()))
    total_success = (0, 0)
    total_fail = (0, 0)
    total_unmapped = count_grouped(unmapped)

    success_copied_by_label: dict[str, list[str]] = {}

    for repo_name, info in repo_base_map.items():
        execute: bool = info["execute"]
        svr_path_pairs: list[tuple[str, str]] = info["svr_path"]
        base_path: Path = info["base"]
        repo_src_root: Path = info["root"]
        repo_src_path: str = info.get("src_path", "")

        print("==================================================================")
        print(f"[{repo_name}]")
        print("------------------------------------------------------------------")

        if not execute:
            print("execution disabled")
            print("==================================================================")
            print()
            continue

        targets = repo_grouped.get(repo_name, {})
        if not targets:
            print("empty")
            print("==================================================================")
            print()
            continue

        build_file = info.get("build_file")
        if not build_file:
            print("build_file is empty")
            print("==================================================================")
            print()
            continue

        repo_root = copy_root / repo_name
        ensure_empty_dir(repo_root)

        copied_cnt, skipped_cnt, copied_files = copy_worklist_files_to_repo_src(
            repo_src_root=repo_src_root,
            repo_out_root=repo_root,
            src_path=repo_src_path,
            worklist_inputs=raw_inputs,
        )

        if copied_cnt or skipped_cnt:
            sp = _clean_rel_path(repo_src_path)
            dst_base = (repo_root / sp) if sp else repo_root
            print(f"[SOURCE] {dst_base} (copied={copied_cnt}, skipped={skipped_cnt})")
            for p in copied_files:
                print(f"  - {p}")

        run_ant_build_one(str(ant_cmd), str(build_file), str(base_path))

        target_roots = normalize_copy_roots(svr_path_pairs, repo_root)
        prefix_by_label = build_prefix_by_label(svr_path_pairs)

        print(f"[COPY] {format_copy_block(target_roots)}")
        print("-------")

        logs = copy_grouped_and_log_multi(base_path, target_roots, targets)

        success_grouped: dict[Path, list[Path]] = {}
        fail_grouped: dict[Path, list[Path]] = {}

        for status, changed, copied_list, src_list in logs:
            if status == "O":
                print(f"[O] {changed} -> {format_copy_block(copied_list)}")
                if is_orin_log:
                    print(f"    {format_orin_block(src_list, orin_map)}")
                success_grouped[changed] = src_list
                add_success_copied_by_label(success_copied_by_label, repo_root, copied_list, prefix_by_label)
            else:
                print(f"[X] {changed}")
                if is_orin_log:
                    print(f"    {format_orin_block(src_list, orin_map)}")
                fail_grouped[changed] = src_list

        total_success = add_counts(total_success, count_grouped(success_grouped))
        total_fail = add_counts(total_fail, count_grouped(fail_grouped))

        print("==================================================================")
        print()

    print_unmapped(unmapped, is_orin_log, orin_map)
    print_success_by_label(success_copied_by_label)

    print(
        f"total({total_all[0]}/{total_all[1]}), "
        f"success({total_success[0]}/{total_success[1]}), "
        f"fail({total_fail[0]}/{total_fail[1]}), "
        f"fail-unmapped({total_unmapped[0]}/{total_unmapped[1]})"
    )


def main() -> None:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    summary_file = config.get("summary_file")
    work_summary_file = config.get("work_summary_file")

    original_stdout = sys.stdout
    tee_files = []

    try:
        streams = [sys.__stdout__]

        for fp in (summary_file, work_summary_file):
            if fp:
                p = Path(fp)
                p.parent.mkdir(parents=True, exist_ok=True)
                fobj = open(p, "w", encoding="utf-8")
                tee_files.append(fobj)
                streams.append(fobj)

        if len(streams) > 1:
            sys.stdout = Tee(*streams)

        run_pipeline(config)

    finally:
        sys.stdout = original_stdout
        for fobj in tee_files:
            try:
                fobj.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
