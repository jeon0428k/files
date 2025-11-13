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
        repo_path = repo.get("name", "unknown")
        repo_name = Path(repo_path).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        processor.fm.append_log(repo_name, f"❌ 처리 실패: {e}")
        processor.fm.session_log(repo_name, f"❌ 처리 실패: {e}")

def main():
    config = load_config("config.yml")

    server = config["github"]["server"]
    token = config["github"]["token"]
    branch = config["github"].get("branch", "main")

    repo_base_dir = Path(config["paths"]["repo_dir"]).resolve()
    copy_dir = Path(config["paths"]["copy_dir"]).resolve()
    logs_dir = Path(config["paths"]["logs_dir"]).resolve()
    back_dir = Path(config["paths"]["back_dir"]).resolve()
    ant_cmd = config["paths"]["ant_cmd"]

    # 실행 전에 폴더 생성
    for d in [repo_base_dir, copy_dir, logs_dir, back_dir]:
        d.mkdir(parents=True, exist_ok=True)

    repos = config["repositories"]

    file_manager = FileManager(copy_dir, logs_dir, back_dir)
    git_manager = GitManager(server, token, branch, file_manager)
    processor = RepoProcessor(git_manager, file_manager, repo_base_dir, ant_cmd)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_single_repo, processor, repo) for repo in repos]
        for future in as_completed(futures):
            future.result()

if __name__ == "__main__":
    main()
