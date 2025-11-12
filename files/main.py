from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from modules.util import load_config
from modules.git_manager import GitManager
from modules.file_manager import FileManager
from modules.repo_processor import RepoProcessor

def process_single_repo(processor, repo):
    try:
        processor.process_repo(repo)
    except Exception as e:
        repo_name = repo.get("name", "unknown")
        processor.fm._write_log(repo_name, f"❌ 처리 실패: {e}")
        print(f"❌ {repo_name} 처리 중 에러: {e}")

def main():
    config = load_config("config.yml")

    server = config["github"]["server"]
    token = config["github"]["token"]
    branch = config["github"].get("branch", "main")

    # 절대경로 변환
    repo_base_dir = Path(config["paths"]["repo_dir"]).resolve()
    copy_base_dir = Path(config["paths"]["copy_target"]).resolve()
    log_base_dir = Path(config["paths"]["log_dir"]).resolve()

    repos = config["repositories"]

    git_manager = GitManager(server, token, branch)
    file_manager = FileManager(copy_base_dir, log_base_dir)
    processor = RepoProcessor(git_manager, file_manager, repo_base_dir)

    # 멀티스레드 처리
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_single_repo, processor, repo) for repo in repos]
        for future in as_completed(futures):
            future.result()  # 예외 발생 시 로그 기록

if __name__ == "__main__":
    main()