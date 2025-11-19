from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter
from datetime import datetime

from modules.util import load_config
from modules.git_manager import GitManager
from modules.file_manager import FileManager
from modules.repo_processor import RepoProcessor


# -------------------------------------------------------------
# worklist 파일 읽기
# -------------------------------------------------------------
def load_worklist(worklist_path: Path) -> list[str]:
    if not worklist_path.exists():
        raise FileNotFoundError(f"Worklist file not found: {worklist_path}")
    with open(worklist_path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f.readlines() if x.strip()]


# -------------------------------------------------------------
# copy_list 분석
# -------------------------------------------------------------
def analyze_copy_list(repo: dict, copy_list: list[str]):
    repo["raw_copy_list"] = list(copy_list)
    repo["copy_count_map"] = Counter(copy_list)
    repo["unique_copy_list"] = list(repo["copy_count_map"].keys())


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


# -------------------------------------------------------------
# config copy_list 로드
# -------------------------------------------------------------
def load_copy_list_from_config(repo: dict):
    copy_list = repo.get("copy_list", []) or []
    analyze_copy_list(repo, copy_list)


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
        count_map = repo.get("copy_count_map", {})

        exist_list = repo.get("exist_files", [])
        missing_list = repo.get("missing_files", [])

        raw_count = len(raw_list)
        unique_count = len(set(raw_list))
        exist_raw = sum(count_map.get(x, 0) for x in exist_list)
        exist_unique = len(set(exist_list))
        missing_raw = sum(count_map.get(x, 0) for x in missing_list)
        missing_unique = len(set(missing_list))

        repo_items |= set(raw_list)

        if not is_target:
            continue

        lines.append(f"===== {repo_name} =====")
        console_lines.append(f"===== {repo_name} =====")

        exec_str = ", ".join(exec_list)
        lines.append(f"Execution mode: {exec_str}")
        console_lines.append(f"Execution mode: {exec_str}")

        # -------------------------------
        # log_file_check_summary() 동일 방식
        # 존재 파일 먼저 → 정렬 출력
        # -------------------------------
        for item in sorted(set(exist_list)):
            raw_cnt = count_map.get(item, 1)
            msg = f"[O] {item},{raw_cnt}"
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

        # summary line
        summary_line = (
            f"total: {raw_count}({unique_count}), "
            f"exists: {exist_raw}({exist_unique}), "
            f"missing: {missing_raw}({missing_unique})"
        )

        lines.append(summary_line)
        console_lines.append(summary_line)
        lines.append("")
        console_lines.append("")

        all_raw_items.extend(raw_list)
        all_unique_items |= set(raw_list)

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

    # 전체 exist / missing 수집
    total_exist_raw = sum(
        repo["copy_count_map"].get(x, 0)
        for repo in repos
        for x in repo.get("exist_files", [])
    )
    total_exist_unique = len(
        set(x for repo in repos for x in repo.get("exist_files", []))
    )

    total_missing_raw = sum(
        repo["copy_count_map"].get(x, 0)
        for repo in repos
        for x in repo.get("missing_files", [])
    )
    total_missing_unique = len(
        set(x for repo in repos for x in repo.get("missing_files", []))
    )

    lines.append("===== summary =====")
    console_lines.append("===== summary =====")

    summary_final = (
        f"total: {all_raw}({all_unique}), "
        f"exists: {total_exist_raw}({total_exist_unique}), "
        f"missing: {total_missing_raw}({total_missing_unique}), "
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
    config = load_config("config.yml")

    is_single = config.get("is_single", False)
    is_worklist = config.get("is_worklist", False)

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

    for d in [repo_base_dir, copy_dir, logs_dir, back_dir]:
        d.mkdir(parents=True, exist_ok=True)

    repos = config["repositories"]

    # worklist 모드 처리
    if is_worklist:
        worklist = load_worklist(worklist_file)
        distribute_worklist_to_repos(repos, worklist)
    else:
        worklist = None
        for repo in repos:
            load_copy_list_from_config(repo)

    # Manager 생성
    fm = FileManager(copy_dir, logs_dir, back_dir)
    gm = GitManager(server, token, global_branch, fm)
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

    # ★★★★★ 모든 repo 처리 후 summary 생성 ★★★★★
    write_summary(copy_dir, repos, worklist)


if __name__ == "__main__":
    main()