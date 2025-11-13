import os
import shutil
import subprocess
from pathlib import Path

class GitManager:
    def __init__(self, server: str, token: str, branch: str = "main", file_manager=None):
        self.server = server
        self.token = token
        self.branch = branch
        self.fm = file_manager

    def _auth_url(self, repo_path: str) -> str:
        return f"{self.server}/{repo_path}".replace("https://", f"https://{self.token}@")

    def clone_or_pull(self, repo_path: str, base_dir: str, git_mode: str = "pull") -> Path:
        base_dir = Path(base_dir).resolve()
        repo_name = Path(repo_path).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        local_dir = base_dir / repo_name
        local_dir.parent.mkdir(parents=True, exist_ok=True)
        auth_url = self._auth_url(repo_path)

        def log_msg(msg: str):
            if self.fm:
                self.fm.append_log(repo_name, msg)
                self.fm.session_log(repo_name, msg)
            else:
                print(msg)

        if git_mode == "clean" and local_dir.exists():
            log_msg(f"🧹 [{git_mode}] exists dir delete: {repo_path}")
            def remove_readonly(func, path, excinfo):
                os.chmod(path, 0o777)
                func(path)
            shutil.rmtree(local_dir, onerror=remove_readonly)

        if not local_dir.exists():
            log_msg(f"📦 [{git_mode}] clone: {repo_path} → {local_dir}")
            subprocess.run(["git", "clone", "-b", self.branch, auth_url, str(local_dir)], check=True)
        else:
            if git_mode == "pull":
                log_msg(f"📥 [{git_mode}] pull: {repo_path}")
                subprocess.run(["git", "fetch", "origin"], cwd=local_dir, check=True)
                subprocess.run(["git", "reset", "--hard", f"origin/{self.branch}"], cwd=local_dir, check=True)

        return local_dir.resolve()
