import sys
import yaml
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

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
    """
    config.yml repositories 항목에서 repo별 설정을 정규화해서 저장
    - dir (단일 문자열) -> svr_path (리스트) 로 변경
    - svr_path 가 비어있을 수도 있음 (그 경우 repo_root 바로 아래로 복사)
    """
    repo_base_map: dict[str, dict] = {}
    for r in repositories:
        name = r["name"]
        root = Path(r["root"]).resolve()
        base = (root / r["path"]).resolve()

        # dir 호환(기존 설정이 남아있으면 단일값을 리스트로)
        svr_path = r.get("svr_path", None)
        if svr_path is None:
            legacy_dir = r.get("dir", "")
            svr_path = [legacy_dir] if legacy_dir else []
        elif isinstance(svr_path, str):
            svr_path = [svr_path]
        else:
            svr_path = svr_path or []

        repo_base_map[name] = {
            "name": name,
            "root": root,
            "base": base,
            "svr_path": svr_path,
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

        if copied_list:
            logs.append(("O", changed, copied_list, src_list))
        else:
            logs.append(("X", changed, [], src_list))

    return sorted(logs, key=lambda x: (0 if x[0] == "O" else 1, str(x[1])))


def format_orin_block(src_list: list[Path]) -> str:
    count = len(src_list)
    joined = ", ".join(str(p) for p in src_list)
    return f"({count})[{joined}]"


def format_copy_block(paths: list[Path]) -> str:
    if not paths:
        return ""
    if len(paths) == 1:
        return str(paths[0])
    return f"({len(paths)})[{', '.join(str(p) for p in paths)}]"


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


def normalize_svr_paths(svr_paths: list[str], repo_root: Path) -> list[Path]:
    """
    - svr_path 가 비어있으면 repo_root 하나만 반환 (기본 동작)
    - 값이 있으면 repo_root / 각 svr_path 반환
    """
    if not svr_paths:
        repo_root.mkdir(parents=True, exist_ok=True)
        return [repo_root]

    roots: list[Path] = []
    for p in svr_paths:
        p = str(p).strip().strip("/").strip("\\")
        root = repo_root / p if p else repo_root
        root.mkdir(parents=True, exist_ok=True)
        roots.append(root)
    return roots


# ----------------------------
# 성공 copy 경로를 dev/prd(첫 path) 기준으로 모아 출력
# ----------------------------
def add_success_copied_by_label(
    success_by_label: dict[str, list[str]],
    repo_root: Path,
    copied_list: list[Path],
) -> None:
    """
    copied_list(실제 복사된 경로)를 repo_root 기준 상대경로로 만든 뒤,
    첫 세그먼트를 label(dev/prd 등)로 사용하고 label 이후 경로를 '/...' 형태로 저장한다.

    예) repo_root/dev/a/WEB-INF/...  -> label='dev', store='/a/WEB-INF/...'
    """
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


# ----------------------------
# main try 블록 내용을 함수로 분리
# ----------------------------
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

    raw_inputs = read_worklist(worklist_file)
    grouped_all = apply_transforms_grouped(raw_inputs, repo_base_map)
    repo_grouped, unmapped = classify_grouped(grouped_all, repo_base_map)

    total_all = (len(grouped_all), sum(len(v) for v in grouped_all.values()))

    total_success = (0, 0)
    total_fail = (0, 0)
    total_unmapped = count_grouped(unmapped)

    # dev/prd 등 첫 path 기준으로 성공 copy 경로만 모으기
    success_copied_by_label: dict[str, list[str]] = {}

    for repo_name, info in repo_base_map.items():
        execute: bool = info["execute"]
        svr_paths: list[str] = info["svr_path"]
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

        target_roots = normalize_svr_paths(svr_paths, repo_root)

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
                    print(f"    {format_orin_block(src_list)}")
                success_grouped[changed] = src_list

                add_success_copied_by_label(success_copied_by_label, repo_root, copied_list)
            else:
                print(f"[X] {changed}")
                if is_orin_log:
                    print(f"    {format_orin_block(src_list)}")
                fail_grouped[changed] = src_list

        total_success = add_counts(total_success, count_grouped(success_grouped))
        total_fail = add_counts(total_fail, count_grouped(fail_grouped))

        print("=================================\n")

    print_unmapped(unmapped, is_orin_log)

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

    # summary_file 옵션 처리 (없으면 콘솔만, 있으면 덮어쓰기)
    summary_file = config.get("summary_file")
    tee_file = None
    original_stdout = sys.stdout

    if summary_file:
        summary_path = Path(summary_file)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        tee_file = open(summary_path, "w", encoding="utf-8")
        sys.stdout = Tee(sys.__stdout__, tee_file)

    try:
        run_pipeline(config)
    finally:
        sys.stdout = original_stdout
        if tee_file:
            tee_file.close()


if __name__ == "__main__":
    main()
