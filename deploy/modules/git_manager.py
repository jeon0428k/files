import os
import shutil
import subprocess
from pathlib import Path


class GitManager:
    def __init__(self, server, token, branch, file_manager):
        self.server = server
        self.token = token
        self.branch = branch
        self.fm = file_manager

    # Git 인증 URL 생성
    def _auth_url(self, repo_path: str):
        return f"{self.server}/{repo_path}".replace("https://", f"https://{self.token}@")

    # clone 또는 pull 실행
    def clone_or_pull(self, repo_path: str, base_dir: Path, mode="pull"):
        repo_name = Path(repo_path).stem
        dir_path = base_dir / repo_name
        auth_url = self._auth_url(repo_path)

        # 전체로그 + (ALL 모드 시) 세션로그 + 콘솔에 동일 메시지 출력
        def log(msg: str):
            self.fm.dual_log(repo_name, msg)

        # clean 모드 → 기존 디렉토리 삭제
        if mode == "clean" and dir_path.exists():
            log("Clean mode → Removing existing directory")

            def rw(func, path, exc):
                os.chmod(path, 0o777)
                func(path)

            shutil.rmtree(dir_path, onerror=rw)

        # clone
        if not dir_path.exists():
            log("Clone started")
            subprocess.run(["git", "clone", "-b", self.branch, auth_url, str(dir_path)], check=True)

        # pull
        else:
            if mode == "pull":
                log("Pull executed")
                subprocess.run(["git", "fetch", "origin"], cwd=dir_path, check=True)
                subprocess.run(["git", "reset", "--hard", f"origin/{self.branch}"], cwd=dir_path, check=True)

        return dir_path
