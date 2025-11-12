from modules.git_manager import GitManager
from modules.file_manager import FileManager

class RepoProcessor:
    def __init__(self, git_manager: GitManager, file_manager: FileManager, repo_base_dir: str):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = repo_base_dir
        self.backup_done = False  # copy_target 전체 백업 여부

    def process_repo(self, repo_info: dict):
        repo_name = repo_info["name"]
        copy_list = repo_info.get("copy_list")
        transform_path = repo_info.get("transform_path")

        print(f"\n🚀 처리 중: {repo_name}")
        repo_dir = self.git.clone_or_pull(repo_name, self.repo_base_dir)

        if not copy_list:
            msg = f"⏩ Skip: {repo_name} (copy_list 없음)"
            print(msg)
            self.fm._write_log(repo_name, msg)
            return

        # copy_target 전체 백업 한 번만 수행
        if not self.backup_done:
            self.fm.backup_copy_target()
            self.backup_done = True

        self.fm.copy_files(repo_dir, repo_name, copy_list, transform_path)