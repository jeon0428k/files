from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from fnmatch import fnmatch
from collections import Counter
from datetime import datetime
import shutil  # ★ ADD

from modules.util import load_config
from modules.git_manager import GitManager
from modules.file_manager import FileManager
from modules.repo_processor import RepoProcessor


# -------------------------------------------------------------
# 경로 정규화: 선행 (/, gemswas/) 제거
# -------------------------------------------------------------
def normalize_path(p: str) -> str:
    if not p:
        return p

    p = p.strip()

    # 선행 / 모두 제거
    while p.startswith("/"):
        p = p[1:]

    # 선행 gemswas/ 제거
    if p.startswith("gemswas/"):
        p = p[len("gemswas/"):]

    return p


# -------------------------------------------------------------
# 리스트 경로 정규화
# -------------------------------------------------------------
def normalize_paths_in_list(paths: list[str] | None) -> list[str]:
    if not paths:
        return []
    return [normalize_path(x) for x in paths]


# -------------------------------------------------------------
# worklist 파일 읽기
# -------------------------------------------------------------
def load_worklist(worklist_path: Path) -> list[str]:
    if not worklist_path.exists():
        raise FileNotFoundError(f"Worklist file not found: {worklist_path}")
    with open(worklist_path, "r", encoding="utf-8") as f:
        return [normalize_path(x.strip()) for x in f.readlines() if x.strip()]


# -------------------------------------------------------------
# copy_list 분석
# -------------------------------------------------------------
def analyze_copy_list(repo: dict, copy_list: list[str]):
    repo["raw_copy_list"] = list(copy_list)
    repo["copy_count_map"] = Counter(copy_list)
    repo["unique_copy_list"] = list(repo["copy_count_map"].keys())


# -------------------------------------------------------------
# db_list 분석
# -------------------------------------------------------------
def analyze_db_list(repo: dict, db_list: list[str]):
    repo["raw_db_list"] = list(db_list)
    repo["db_count_map"] = Counter(db_list)
    repo["unique_db_list"] = list(repo["db_count_map"].keys())


# -------------------------------------------------------------
# 패턴 매칭 (db_file_paths 용)
# - FileManager의 exclude/glob과 동일하게 fnmatch 사용
# -------------------------------------------------------------
def match_any_pattern(path: str, patterns: list[str]) -> bool:
    if not path or not patterns:
        return False
    p = normalize_path(path).replace("\\", "/")
    for pat in patterns:
        pat_n = normalize_path(pat).replace("\\", "/")
        if fnmatch(p, pat_n):
            return True
    return False


# -------------------------------------------------------------
# worklist 분배
# -------------------------------------------------------------
def distribute_worklist_to_repos(repos: list[dict], worklist: list[str]):
    for repo in repos:
        prefixes = repo.get("worklist_prefixes", [])
        matched = []
        for line in worklist:
            for prefix in prefixes:
                if line.startswith(prefix):
                    matched.append(line)
                    break
        analyze_copy_list(repo, matched)

        db_patterns = repo.get("db_file_paths", []) or []
        db_matched = []
        if db_patterns:
            for line in worklist:
                if match_any_pattern(line, db_patterns):
                    db_matched.append(line)
        analyze_db_list(repo, db_matched)


# -------------------------------------------------------------
# repository 단일 실행 래퍼
# -------------------------------------------------------------
def process_single_repo(processor: RepoProcessor, repo: dict):
    repo_name = Path(repo.get("name")).stem
    try:
        processor.process_repo(repo)
    except Exception as e:
        processor.fm.dual_log(repo_name, f"Processing failed: {e}")


# -------------------------------------------------------------
# SUMMARY 기능
# -------------------------------------------------------------
def write_summary(copy_dir: Path, repos: list[dict], worklist: list[str] | None):
    summary_file = copy_dir / "summary.log"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_time = f"> {ts}"

    lines = [header_time, ""]
    console_lines = [header_time, ""]

    all_raw_items = []
    all_unique_items = set()

    others_raw = []
    others_unique = set()

    repo_items = set()

    for repo in repos:
        repo_name = Path(repo["name"]).stem
        exec_list = repo.get("execute", [])
        is_target = any(x in exec_list for x in ("all", "copy"))

        raw_list = repo.get("raw_copy_list", [])
        count_map = repo.get("copy_count_map", {}) or {}

        raw_db_list = repo.get("raw_db_list", []) or []
        db_count_map = repo.get("db_count_map", {}) or {}

        exist_list = repo.get("exist_files", []) or []
        missing_list = repo.get("missing_files", []) or []
        excluded_list = repo.get("excluded_files", []) or []

        db_exist_list = repo.get("db_exist_files", []) or []
        db_missing_list = repo.get("db_missing_files", []) or []

        raw_count = len(raw_list)
        unique_count = len(set(raw_list))

        exist_raw = sum(count_map.get(x, 0) for x in exist_list)
        exist_unique = len(set(exist_list))

        missing_raw = sum(count_map.get(x, 0) for x in missing_list)
        missing_unique = len(set(missing_list))

        excluded_raw = sum(count_map.get(x, 0) for x in excluded_list)
        excluded_unique = len(set(excluded_list))

        db_raw_count = len(raw_db_list)
        db_unique_count = len(set(raw_db_list))

        db_exist_raw = sum(db_count_map.get(x, 0) for x in db_exist_list)
        db_exist_unique = len(set(db_exist_list))

        db_missing_raw = sum(db_count_map.get(x, 0) for x in db_missing_list)
        db_missing_unique = len(set(db_missing_list))

        # summary 출력은 기존 필드(total/exists/missing/excluded)에 DB를 합산한다.
        total_raw = raw_count + db_raw_count
        total_unique = unique_count + db_unique_count

        total_exist_raw = exist_raw + db_exist_raw
        total_exist_unique = exist_unique + db_exist_unique

        total_missing_raw = missing_raw + db_missing_raw
        total_missing_unique = missing_unique + db_missing_unique

        # excluded는 기존(copy_exclude_paths)만 해당. DB는 excluded 개념 없음.
        total_excluded_raw = excluded_raw
        total_excluded_unique = excluded_unique

        repo_items |= set(raw_list)
        repo_items |= set(raw_db_list)

        if not is_target:
            continue

        lines.append(f"===== {repo_name} =====")
        console_lines.append(f"===== {repo_name} =====")

        exec_str = ", ".join(exec_list)
        lines.append(f"Execution mode: {exec_str}")
        console_lines.append(f"Execution mode: {exec_str}")

        # -------------------------------
        # 존재 파일 먼저 → 정렬 출력
        # -------------------------------
        for item in sorted(set(exist_list)):
            raw_cnt = count_map.get(item, 1)
            msg = f"[O] {item},{raw_cnt}"
            lines.append(msg)
            console_lines.append(msg)

        # -------------------------------
        # DB 존재 파일
        # -------------------------------
        for item in sorted(set(db_exist_list)):
            raw_cnt = db_count_map.get(item, 1)
            msg = f"[O] (DB) {item},{raw_cnt}"
            lines.append(msg)
            console_lines.append(msg)

        # -------------------------------
        # 제외 파일 정렬 출력
        # -------------------------------
        for item in sorted(set(excluded_list)):
            raw_cnt = count_map.get(item, 1)
            msg = f"[-] {item},{raw_cnt}"
            lines.append(msg)
            console_lines.append(msg)

        # -------------------------------
        # 미존재 파일 정렬 출력
        # -------------------------------
        for item in sorted(set(missing_list)):
            raw_cnt = count_map.get(item, 1)
            msg = f"[X] {item},{raw_cnt}"
            lines.append(msg)
            console_lines.append(msg)

        # -------------------------------
        # DB 미존재 파일
        # -------------------------------
        for item in sorted(set(db_missing_list)):
            raw_cnt = db_count_map.get(item, 1)
            msg = f"[X] (DB) {item},{raw_cnt}"
            lines.append(msg)
            console_lines.append(msg)

        # summary line (기존 필드에 DB 합산)
        summary_line = (
            f"total: {total_raw}({total_unique}), "
            f"exists: {total_exist_raw}({total_exist_unique}), "
            f"missing: {total_missing_raw}({total_missing_unique}), "
            f"excluded: {total_excluded_raw}({total_excluded_unique})"
        )

        lines.append(summary_line)
        console_lines.append(summary_line)
        lines.append("")
        console_lines.append("")

        all_raw_items.extend(raw_list)
        all_unique_items |= set(raw_list)
        all_raw_items.extend(raw_db_list)
        all_unique_items |= set(raw_db_list)

    # -------------------------------
    # others 처리 영역
    # -------------------------------
    if worklist:
        unknown = set(worklist) - repo_items
        if unknown:
            lines.append("===== unknown =====")
            console_lines.append("===== unknown =====")

            for item in sorted(unknown):
                raw_cnt = 1
                msg = f"[X] {item},{raw_cnt}"
                lines.append(msg)
                console_lines.append(msg)
                others_raw.append(item)
                others_unique.add(item)

            summary_line = f"total: {len(others_raw)}({len(others_unique)})"
            lines.append(summary_line)
            console_lines.append(summary_line)
            lines.append("")
            console_lines.append("")

    all_raw = len(all_raw_items) + len(others_raw)
    all_unique = len(all_unique_items | others_unique)

    # 전체 exist / missing / excluded 수집
    total_exist_raw = sum(
        (repo.get("copy_count_map", {}) or {}).get(x, 0)
        for repo in repos
        for x in (repo.get("exist_files", []) or [])
    ) + sum(
        (repo.get("db_count_map", {}) or {}).get(x, 0)
        for repo in repos
        for x in (repo.get("db_exist_files", []) or [])
    )
    total_exist_unique = len(
        set(x for repo in repos for x in (repo.get("exist_files", []) or []))
        | set(x for repo in repos for x in (repo.get("db_exist_files", []) or []))
    )

    total_missing_raw = sum(
        (repo.get("copy_count_map", {}) or {}).get(x, 0)
        for repo in repos
        for x in (repo.get("missing_files", []) or [])
    ) + sum(
        (repo.get("db_count_map", {}) or {}).get(x, 0)
        for repo in repos
        for x in (repo.get("db_missing_files", []) or [])
    )
    total_missing_unique = len(
        set(x for repo in repos for x in (repo.get("missing_files", []) or []))
        | set(x for repo in repos for x in (repo.get("db_missing_files", []) or []))
    )

    total_excluded_raw = sum(
        (repo.get("copy_count_map", {}) or {}).get(x, 0)
        for repo in repos
        for x in (repo.get("excluded_files", []) or [])
    )
    total_excluded_unique = len(
        set(x for repo in repos for x in (repo.get("excluded_files", []) or []))
    )

    lines.append("===== summary =====")
    console_lines.append("===== summary =====")

    summary_final = (
        f"total: {all_raw}({all_unique}), "
        f"exists: {total_exist_raw}({total_exist_unique}), "
        f"missing: {total_missing_raw}({total_missing_unique}), "
        f"excluded: {total_excluded_raw}({total_excluded_unique}), "
        f"unknown: {len(others_raw)}({len(others_unique)})"
    )

    lines.append(summary_final)
    console_lines.append(summary_final)

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(console_lines))


# -------------------------------------------------------------
# main
# -------------------------------------------------------------
def main():
    config = load_config("config/config.yml")

    is_single = config.get("is_single", False)
    is_worklist = config.get("is_worklist", False)

    git_commits_date = config.get("git_commits_date")

    server = config["github"]["server"]
    token = config["github"]["token"]
    global_branch = config["github"]["branch"]

    repo_base_dir = Path(config["paths"]["repo_dir"]).resolve()
    copy_dir = Path(config["paths"]["copy_dir"]).resolve()
    logs_dir = Path(config["paths"]["logs_dir"]).resolve()
    back_dir = Path(config["paths"]["back_dir"]).resolve()
    ant_cmd = config["paths"]["ant_cmd"]

    worklist_path_str = config["paths"].get("worklist_file", "worklist.txt")
    worklist_file = Path(worklist_path_str).resolve()

    # ★ ADD: 추가 summary 출력 파일 경로(없으면 None)
    work_summary_file = config["paths"].get("work_summary_file")
    work_summary_path = Path(work_summary_file).resolve() if work_summary_file else None

    for d in [repo_base_dir, copy_dir, logs_dir, back_dir]:
        d.mkdir(parents=True, exist_ok=True)

    repos = config["repositories"]

    # repo별 copy_exclude_paths 경로 정규화
    for repo in repos:
        if "copy_exclude_paths" in repo:
            repo["copy_exclude_paths"] = normalize_paths_in_list(
                repo.get("copy_exclude_paths")
            )
        if "db_file_paths" in repo:
            repo["db_file_paths"] = normalize_paths_in_list(
                repo.get("db_file_paths")
            )

    # worklist 모드 처리
    if is_worklist:
        worklist = load_worklist(worklist_file)
    else:
        worklist = []
        for repo in repos:
            items = repo.get("copy_list", []) or []
            worklist.extend(normalize_path(x) for x in items if str(x).strip())
    distribute_worklist_to_repos(repos, worklist)

    # Manager 생성
    fm = FileManager(copy_dir, logs_dir, back_dir)
    gm = GitManager(server, token, global_branch, fm, git_commits_date=git_commits_date)
    processor = RepoProcessor(gm, fm, repo_base_dir, ant_cmd, global_branch)

    exec_repos = repos

    if not exec_repos:
        print("No repository to execute.")
        return

    # 순차 실행
    if is_single:
        for repo in exec_repos:
            process_single_repo(processor, repo)

    # 병렬 실행
    else:
        with ThreadPoolExecutor(max_workers=5) as exe:
            futures = [exe.submit(process_single_repo, processor, repo) for repo in exec_repos]
            for f in as_completed(futures):
                f.result()

    # ★★★★★ 모든 repo 처리 후 summary 생성 (기존 로직 유지) ★★★★★
    write_summary(copy_dir, repos, worklist)

    # ★ ADD: 추가 경로에도 summary 덮어쓰기 생성
    if work_summary_path:
        src = copy_dir / "summary.log"
        work_summary_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, work_summary_path)  # 덮어쓰기
        print(f"Extra summary written → {work_summary_path}")


if __name__ == "__main__":
    main()
