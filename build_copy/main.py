import sys
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

CONFIG_FILE = "./config/config.yml"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_worklist(worklist_file: str) -> list[Path]:
    p = Path(worklist_file)
    if not p.exists():
        print(f"> {now_str()}")
        print(f"worklist file not found: {p.resolve()}")
        sys.exit(2)

    items: list[Path] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(Path(s))
    return items


def build_repo_base_map(repositories: list[dict]) -> dict[str, dict]:
    repo_base_map: dict[str, dict] = {}
    for r in repositories:
        name = r["name"]
        root = Path(r["root"]).resolve()
        base = (root / r["path"]).resolve()

        repo_base_map[name] = {
            "name": name,
            "root": root,
            "base": base,
            "dir": r["dir"],
            "execute": bool(r.get("execute", False)),
            "trans_path": r.get("trans_path", []) or [],
            "trans_file": r.get("trans_file", []) or [],
        }
    return repo_base_map


def to_posix(s: str) -> str:
    return s.replace("\\", "/")


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

    for raw in inputs:
        src_abs = raw.expanduser().resolve()
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
        print(f"remove dir: {p}")
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def copy_grouped_and_log(
    base_path: Path,
    target_root: Path,
    grouped: dict[Path, list[Path]],
) -> list[tuple[str, Path, Optional[Path], list[Path]]]:
    logs: list[tuple[str, Path, Optional[Path], list[Path]]] = []

    for changed, src_list in grouped.items():
        if not changed.exists():
            logs.append(("X", changed, None, src_list))
            continue

        try:
            rel = changed.relative_to(base_path)
        except Exception:
            logs.append(("X", changed, None, src_list))
            continue

        try:
            copied = target_root / rel
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(changed, copied)
            logs.append(("O", changed, copied, src_list))
        except Exception:
            logs.append(("X", changed, None, src_list))

    return sorted(logs, key=lambda x: (0 if x[0] == "O" else 1, str(x[1])))


def format_orin_block(src_list: list[Path]) -> str:
    count = len(src_list)
    joined = ", ".join(str(p) for p in src_list)
    return f"({count})[{joined}]"


def print_unmapped(unmapped: dict[Path, list[Path]], is_orin_log: bool) -> None:
    if not unmapped:
        return
    print("=================================")
    print("[UNMAPPED]")
    print("---------------------------------")
    for changed in sorted(unmapped.keys(), key=lambda x: str(x)):
        src_list = unmapped[changed]
        print(f"[X] {changed}")
        if is_orin_log:
            print(f"    {format_orin_block(src_list)}")
    print("=================================")


def count_grouped(grouped: dict[Path, list[Path]]) -> tuple[int, int]:
    changed_cnt = len(grouped)
    orin_cnt = sum(len(v) for v in grouped.values())
    return changed_cnt, orin_cnt


def add_counts(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def main():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print(f"> {now_str()}\n")

    copy_root = Path(config["copy_dir"])
    worklist_file = config.get("worklist_file")
    if not worklist_file:
        print("worklist_file is required")
        sys.exit(2)

    is_orin_log = bool(config.get("is_orin_log", True))

    repositories = config.get("repositories", []) or []
    if not repositories:
        print("repositories is empty")
        sys.exit(2)

    repo_base_map = build_repo_base_map(repositories)

    raw_inputs = read_worklist(worklist_file)
    grouped_all = apply_transforms_grouped(raw_inputs, repo_base_map)
    repo_grouped, unmapped = classify_grouped(grouped_all, repo_base_map)

    total_all = (len(grouped_all), sum(len(v) for v in grouped_all.values()))

    total_success = (0, 0)
    total_fail = (0, 0)
    total_unmapped = count_grouped(unmapped)

    for repo_name, info in repo_base_map.items():
        execute: bool = info["execute"]
        repo_dir: str = info["dir"]
        base_path: Path = info["base"]

        print("=================================")
        print(f"[{repo_name}]")
        print("---------------------------------")

        if not execute:
            print("execution disabled")
            print("=================================\n")
            continue

        targets = repo_grouped.get(repo_name, {})
        if not targets:
            print("empty")
            print("=================================\n")
            continue

        repo_root = copy_root / repo_name
        ensure_empty_dir(repo_root)

        target_root = repo_root / repo_dir
        target_root.mkdir(parents=True, exist_ok=True)

        print(f"target root: {base_path}")
        print(f"copy root: {target_root}")
        print("----------")

        logs = copy_grouped_and_log(base_path, target_root, targets)

        success_grouped: dict[Path, list[Path]] = {}
        fail_grouped: dict[Path, list[Path]] = {}

        for status, changed, copied, src_list in logs:
            if status == "O":
                print(f"[O] {changed} -> {copied}")
                if is_orin_log:
                    print(f"    {format_orin_block(src_list)}")
                success_grouped[changed] = src_list
            else:
                print(f"[X] {changed}")
                if is_orin_log:
                    print(f"    {format_orin_block(src_list)}")
                fail_grouped[changed] = src_list

        total_success = add_counts(total_success, count_grouped(success_grouped))
        total_fail = add_counts(total_fail, count_grouped(fail_grouped))

        print("=================================\n")

    print_unmapped(unmapped, is_orin_log)

    print(
        f"total({total_all[0]}/{total_all[1]}), "
        f"success({total_success[0]}/{total_success[1]}), "
        f"fail({total_fail[0]}/{total_fail[1]}), "
        f"fail-unmapped({total_unmapped[0]}/{total_unmapped[1]})"
    )


if __name__ == "__main__":
    main()
