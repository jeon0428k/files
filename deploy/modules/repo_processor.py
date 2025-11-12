from modules.git_manager import GitManager
from modules.file_manager import FileManager

class RepoProcessor:
    def __init__(self, git_manager: GitManager, file_manager: FileManager, repo_base_dir: str):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = repo_base_dir

    def process_repo(self, repo_info: dict):
        repo_name = repo_info["name"]
        copy_list = repo_info.get("copy_list")
        print(f"\n🚀 처리 중: {repo_name}")
        repo_dir = self.git.clone_or_pull(repo_name, self.repo_base_dir)
        repo_folder_name = repo_dir.name
        if not copy_list:
            msg = f"⏩ Skip: {repo_name} (copy_list 없음)"
            print(msg)
            self.fm._write_log(repo_folder_name, msg)
            return
        self.fm.backup_if_exists(repo_folder_name)
        self.fm.copy_files(repo_dir, repo_folder_name, copy_list)