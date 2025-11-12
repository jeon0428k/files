import subprocess
from pathlib import Path

class GitManager:
    def __init__(self, server: str, token: str, branch: str = "main"):
        self.server = server
        self.token = token
        self.branch = branch

    def _auth_url(self, repo_path: str) -> str:
        return f"{self.server}/{repo_path}".replace("https://", f"https://{self.token}@")

    def clone_or_pull(self, repo_path: str, base_dir: str) -> Path:
        base_dir = Path(base_dir).resolve()
        repo_name = Path(repo_path).stem
        local_dir = base_dir / repo_name
        local_dir.parent.mkdir(parents=True, exist_ok=True)
        auth_url = self._auth_url(repo_path)

        if not local_dir.exists():
            print(f"📦 Clone: {repo_path} → {local_dir}")
            subprocess.run(["git", "clone", "-b", self.branch, auth_url, str(local_dir)], check=True)
        else:
            print(f"📥 Pull (강제 덮어쓰기): {repo_path}")
            subprocess.run(["git", "fetch", "origin"], cwd=local_dir, check=True)
            subprocess.run(["git", "reset", "--hard", f"origin/{self.branch}"], cwd=local_dir, check=True)
        return local_dir.resolve()