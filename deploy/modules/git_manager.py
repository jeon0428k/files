import os
import shutil
import subprocess
from pathlib import Path


class GitManager:
    def __init__(self, server, token, global_branch, file_manager, git_commits_date=None):
        self.server = server              # GitHub 서버 주소
        self.token = token                # GitHub Personal Token
        self.global_branch = global_branch  # default branch (fallback)
        self.fm = file_manager            # FileManager 인스턴스
        self.git_commits_date = git_commits_date

    # ---------------------------------------------------------
    # 인증 URL 생성 (토큰 삽입)
    # ---------------------------------------------------------
    def _auth_url(self, repo_path: str):
        return f"{self.server}/{repo_path}".replace("https://", f"https://{self.token}@")

    # ---------------------------------------------------------
    # clone 또는 pull 실행
    # ---------------------------------------------------------
    def clone_or_pull(self, repo_path: str, base_dir: Path, mode="pull", branch=None):
        """
        branch: repo_processor에서 전달받은 repository 전용 branch
        """

        repo_name = Path(repo_path).stem
        dir_path = base_dir / repo_name
        auth_url = self._auth_url(repo_path)

        # 사용 branch: repo별 branch → global branch 순
        use_branch = branch or self.global_branch

        def log(msg: str):
            self.fm.dual_log(repo_name, msg)

        # clean 모드이면 기존 폴더 제거
        if mode == "clean" and dir_path.exists():
            log("Clean mode → Removing existing directory")

            def rw(func, path, exc):
                os.chmod(path, 0o777)
                func(path)

            shutil.rmtree(dir_path, onerror=rw)

        # clone
        if not dir_path.exists():
            log(f"Clone started (branch: {use_branch})")
            subprocess.run(["git", "clone", "-b", use_branch, auth_url, str(dir_path)], check=True)

        else:
            # pull
            if mode == "pull":
                log(f"Pull executed (branch: {use_branch})")

                subprocess.run(["git", "fetch", "origin"], cwd=dir_path, check=True)
                subprocess.run(["git", "reset", "--hard", f"origin/{use_branch}"], cwd=dir_path, check=True)

                if self.git_commits_date:
                    try:
                        cmd = [
                            "git", "log",
                            f"--since={self.git_commits_date}",
                            "--pretty=format:%h %an %ad %s",
                            "--date=iso",
                            "--name-only",
                        ]

                        result = subprocess.run(
                            cmd,
                            cwd=dir_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            check=True,
                        )

                        if result.stdout.strip():
                            log(f"Commits after specified date (since: {self.git_commits_date})")

                            prev_blank = True

                            for line in result.stdout.splitlines():
                                if not line.strip():
                                    prev_blank = True
                                    continue

                                if prev_blank:
                                    parts = line.split(" ")
                                    if len(parts) >= 5:
                                        commit_hash = parts[0]
                                        author = parts[1]
                                        date = parts[2]
                                        time = parts[3]
                                        # tz = parts[4]  # 출력에 쓰지 않으면 변수 생략 가능
                                        message = " ".join(parts[5:]).strip()
                                        log(f"{commit_hash} {date}_{time} {author} -> {message}")
                                    else:
                                        log(line)
                                    prev_blank = False
                                else:
                                    log(f"  - {line}")
                        else:
                            log(f"No commits after specified date (since: {self.git_commits_date})")

                    except Exception as e:
                        log(f"Failed to read git commits: {e}")

        return dir_path
