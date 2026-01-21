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


# ----------------------------
# summary_file 로 콘솔 출력 동시 기록 (덮어쓰기)
# ----------------------------
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, msg):
        for s in self.streams:
            s.write(msg)
            s.flush()

    def flush(self):
        for s in self.streams:
            s.flush()


def _clean_rel_path(s: str) -> str:
    return str(s).strip().strip("/").strip("\\")


def resolve_worklist_path_abs_only(raw: str) -> Path:
    """
    worklist 항목 경로 해석 규칙:
    - 절대경로만 허용
    - 상대경로면 ABORT
    """
    s = raw.strip()
    p = Path(s).expanduser()
    if not p.is_absolute():
        print(f"[WORKLIST-FAIL] only absolute path allowed: {raw}")
        sys.exit(2)
    return p.resolve()


def read_worklist_abs_only(worklist_file: str) -> tuple[list[Path], dict[Path, list[str]]]:
    p = Path(worklist_file)
    if not p.exists():
        print(f"> {now_str()}")
        print(f"worklist file not found: {p.resolve()}")
        sys.exit(2)

    items: list[Path] = []
    orin_map: dict[Path, list[str]] = {}

    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue

        abs_path = resolve_worklist_path_abs_only(s)
        items.append(abs_path)
        orin_map.setdefault(abs_path, []).append(s)  # 원본 문자열 보존(절대경로 문자열 그대로)

    return items, orin_map


def normalize_svr_path_pairs(raw_svr_path) -> list[tuple[str, str]]:
    """
    svr_path 지원 형태:
      1) ["dev/a", "prd/b"]
      2) [("/wasadmin", "dev/a"), ("/root", "prd/b")]
      3) [["/wasadmin", "dev/a"], ["/root", "prd/b"]]  (YAML 안전 표기)
    return: [(prefix, path), ...]  (path는 비어있으면 제외)
    """
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
    """
    config.yml repositories 항목에서 repo별 설정을 정규화해서 저장
    - dir(레거시) -> svr_path 로 호환
    - svr_path: 내부적으로 list[tuple[prefix, path]] 로 정규화
    """
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
            "svr_path": svr_path_pairs,  # [(prefix, path), ...]
            "execute": bool(r.get("execute", False)),
            "trans_path": r.get("trans_path", []) or [],
            "trans_file": r.get("trans_file", []) or [],
            "build_file": r.get("build_file"),
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
        print(f"remove dir: {p}")
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)


def normalize_copy_roots(svr_path_pairs: list[tuple[str, str]], repo_root: Path) -> list[Path]:
    """
    실제 복사 대상 root 리스트 생성.
    - svr_path 비어있으면 repo_root 1개
    - 있으면 repo_root / path
    """
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
    """
    하나의 changed 파일을 여러 target_root로 복사한다.
    return:
      (status, changed, copied_list, src_list)
      - status: "O" 성공(복사된 대상 1개 이상) / "X" 실패
      - copied_list: 실제로 복사된 경로들
    """
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
    print("=================================")
    print("[UNMAPPED]")
    print("---------------------------------")
    for changed in sorted(unmapped.keys(), key=lambda x: str(x)):
        src_list = unmapped[changed]
        print(f"[X] {changed}")
        if is_orin_log:
            print(f"    {format_orin_block(src_list, orin_map)}")
    print("=================================")


def count_grouped(grouped: dict[Path, list[Path]]) -> tuple[int, int]:
    return len(grouped), sum(len(v) for v in grouped.values())


def add_counts(a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    return a[0] + b[0], a[1] + b[1]


def build_prefix_by_label(svr_path_pairs: list[tuple[str, str]]) -> dict[str, str]:
    """
    (prefix, "dev/a") -> label=dev 에 대해 prefix 저장
    - label 중복 시 첫 항목 우선(설정 순서)
    """
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
        print("=================================")
        print(f"[{label}]")
        print("---------------------------------")
        for p in items:
            print(p)
        print("=================================\n")


def repo_needs_build(raw_inputs: list[Path], repo_base_map: dict[str, dict]) -> dict[str, bool]:
    """
    worklist 경로가 repositories.root 아래에 하나라도 포함되면 build 대상(True)
    """
    needs: dict[str, bool] = {name: False for name in repo_base_map.keys()}

    for src in raw_inputs:
        for name, info in repo_base_map.items():
            root: Path = info["root"]
            try:
                src.relative_to(root)
                needs[name] = True
            except Exception:
                pass

    return needs


def run_ant_builds(ant_cmd: str, repo_base_map: dict[str, dict], needs_build: dict[str, bool]) -> None:
    """
    repositories 별 build_file 이 있으면 ant_cmd 로 ant build 실행
    단, worklist 경로가 해당 repo.root 아래에 포함되는 경우(needs_build=True)만 실행
    - 실패하면 즉시 종료
    """
    ant = Path(str(ant_cmd)).expanduser()
    if not ant.exists():
        print(f"ant_cmd not found: {ant}")
        sys.exit(2)

    for repo_name, info in repo_base_map.items():
        if not info.get("execute", False):
            continue

        build_file = info.get("build_file")
        if not build_file:
            continue

        if not needs_build.get(repo_name, False):
            print("=================================")
            print(f"[BUILD] {repo_name}")
            print("---------------------------------")
            print("SKIP (no worklist paths under this repositories.root)")
            print("=================================\n")
            continue

        bf = Path(str(build_file)).expanduser()
        if not bf.exists():
            print("=================================")
            print(f"[BUILD] {repo_name}")
            print("---------------------------------")
            print(f"build_file not found: {bf}")
            print("=================================")
            sys.exit(2)

        print("=================================")
        print(f"[BUILD] {repo_name}")
        print("---------------------------------")
        print(f"ant_cmd   : {ant}")
        print(f"build_file: {bf}")
        print("---------------------------------")

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
            print("=================================")
            sys.exit(2)

        if r.stdout:
            print(r.stdout.rstrip())

        if r.returncode != 0:
            print(f"[BUILD-FAIL] returncode={r.returncode}")
            print("=================================")
            sys.exit(2)

        print("[BUILD-OK]")
        print("=================================\n")


def run_pipeline(config: dict) -> None:
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

    # ----------------------------
    # worklist 먼저 읽기 (절대경로만 허용)
    # ----------------------------
    raw_inputs, orin_map = read_worklist_abs_only(worklist_file)

    # ----------------------------
    # repositories.root 포함 여부 기반으로 빌드 대상 결정
    # ----------------------------
    needs_build = repo_needs_build(raw_inputs, repo_base_map)

    # ----------------------------
    # Ant build 실행 (build_file 있는 repo 중 needs_build=True만)
    # ----------------------------
    ant_cmd = config.get("ant_cmd")
    will_build_any = any(
        bool(info.get("build_file"))
        and bool(info.get("execute", False))
        and needs_build.get(name, False)
        for name, info in repo_base_map.items()
    )

    if will_build_any and not ant_cmd:
        print("ant_cmd is required because repositories has build_file to run (matched by worklist)")
        sys.exit(2)

    if will_build_any:
        run_ant_builds(str(ant_cmd), repo_base_map, needs_build)

    # ----------------------------
    # 이후 기존 기능 그대로 실행
    # ----------------------------
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

        target_roots = normalize_copy_roots(svr_path_pairs, repo_root)
        prefix_by_label = build_prefix_by_label(svr_path_pairs)

        print(f"target root: {base_path}")
        print(f"copy roots: {format_copy_block(target_roots)}")
        print("----------")

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

        print("=================================\n")

    print_unmapped(unmapped, is_orin_log, orin_map)

    print()
    print_success_by_label(success_copied_by_label)

    print(
        f"total({total_all[0]}/{total_all[1]}), "
        f"success({total_success[0]}/{total_success[1]}), "
        f"fail({total_fail[0]}/{total_fail[1]}), "
        f"fail-unmapped({total_unmapped[0]}/{total_unmapped[1]})"
    )


def main():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

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
                fobj = open(p, "w", encoding="utf-8")  # 덮어쓰기
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
