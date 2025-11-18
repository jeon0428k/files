from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import Counter

from modules.util import load_config
from modules.git_manager import GitManager
from modules.file_manager import FileManager
from modules.repo_processor import RepoProcessor


# -------------------------------------------------------------
# worklist 파일 읽기
# -------------------------------------------------------------
def load_worklist(worklist_path: Path) -> list[str]:
    """worklist 파일에서 줄 단위 목록을 읽어 리스트 반환"""
    if not worklist_path.exists():
        raise FileNotFoundError(f"Worklist file not found: {worklist_path}")
    with open(worklist_path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f.readlines() if x.strip()]


# -------------------------------------------------------------
# copy_list 를 분석하여 raw/unique/중복 개수 map 생성
# -------------------------------------------------------------
def analyze_copy_list(repo: dict, copy_list: list[str]):
    repo["raw_copy_list"] = list(copy_list)
    repo["copy_count_map"] = Counter(copy_list)
    repo["unique_copy_list"] = list(repo["copy_count_map"].keys())


# -------------------------------------------------------------
# worklist 를 repository별로 prefix 기준으로 분배
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
# repository의 copy_list를 config에서 직접 로드
# -------------------------------------------------------------
def load_copy_list_from_config(repo: dict):
    copy_list = repo.get("copy_list", []) or []
    analyze_copy_list(repo, copy_list)


# -------------------------------------------------------------
# repository 단일 실행 래퍼(예외 처리용)
# -------------------------------------------------------------
def process_single_repo(processor: RepoProcessor, repo: dict):
    repo_name = Path(repo.get("name")).stem
    try:
        processor.process_repo(repo)
    except Exception as e:
        processor.fm.dual_log(repo_name, f"Processing failed: {e}")


# -------------------------------------------------------------
# main
# -------------------------------------------------------------
def main():
    config = load_config("config.yml")

    # 실행 모드 로드
    is_single = config.get("is_single", False)
    is_worklist = config.get("is_worklist", False)

    # 전역 Git 설정
    server = config["github"]["server"]
    token = config["github"]["token"]
    global_branch = config["github"]["branch"]

    # 경로 설정
    repo_base_dir = Path(config["paths"]["repo_dir"]).resolve()
    copy_dir = Path(config["paths"]["copy_dir"]).resolve()
    logs_dir = Path(config["paths"]["logs_dir"]).resolve()
    back_dir = Path(config["paths"]["back_dir"]).resolve()
    ant_cmd = config["paths"]["ant_cmd"]

    # worklist 파일 경로
    worklist_path_str = config["paths"].get("worklist_file", "worklist.txt")
    worklist_file = Path(worklist_path_str).resolve()

    # 필요한 디렉토리 생성
    for d in [repo_base_dir, copy_dir, logs_dir, back_dir]:
        d.mkdir(parents=True, exist_ok=True)

    repos = config["repositories"]

    # worklist 모드 처리
    if is_worklist:
        worklist = load_worklist(worklist_file)
        distribute_worklist_to_repos(repos, worklist)
    else:
        for repo in repos:
            load_copy_list_from_config(repo)

    # Manager 생성
    fm = FileManager(copy_dir, logs_dir, back_dir)
    gm = GitManager(server, token, global_branch, fm)
    processor = RepoProcessor(gm, fm, repo_base_dir, ant_cmd, global_branch)

    # 실행 제외: stop 조건은 process_repo 내부에서 실행됨
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


if __name__ == "__main__":
    main()
