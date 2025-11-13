import shutil
from pathlib import Path
from datetime import datetime
from threading import Lock

class FileManager:
    def __init__(self, copy_dir: str, logs_dir: str, back_dir: str):
        self.copy_dir = Path(copy_dir).resolve()
        self.logs_dir = Path(logs_dir).resolve()
        self.backup_dir = Path(back_dir).resolve()

        # 필요한 폴더 생성
        for d in [self.copy_dir, self.logs_dir, self.backup_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.session_logs = {}  # repo_name -> Path
        self.backup_done = False
        self.lock = Lock()

    # 누적 로그 (파일에만 기록, console 출력 제거)
    def append_log(self, repo_name: str, message: str):
        log_file = self.logs_dir / f"{repo_name}.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        # print(message)  <- 제거

    # 실행 시점 로그 (파일 + console 출력)
    def session_log(self, repo_name: str, message: str):
        if repo_name not in self.session_logs:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_logs[repo_name] = self.copy_dir / f"{timestamp}_{repo_name}.log"
        log_file = self.session_logs[repo_name]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        print(message)  # console 출력은 여기서만

    # copy_dir 백업 (한 번만, thread-safe)
    def backup_copy_target(self):
        with self.lock:
            if self.backup_done:
                return
            if self.copy_dir.exists() and any(self.copy_dir.iterdir()):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.backup_dir / timestamp
                backup_path.mkdir(parents=True, exist_ok=True)
                for item in self.copy_dir.iterdir():
                    shutil.move(str(item), str(backup_path / item.name))
                print(f"📦 전체 백업 완료: {self.copy_dir} → {backup_path}")
            self.backup_done = True

    # 존재 여부 확인
    def check_copy_files_exist(self, repo_dir: Path, copy_list: list[str]) -> tuple[list[str], list[str]]:
        exist_files = []
        missing_files = []
        for rel_path in copy_list:
            src_file = (repo_dir / rel_path).resolve()
            if src_file.exists():
                exist_files.append(rel_path)
            else:
                missing_files.append(rel_path)
        return exist_files, missing_files

    # 실제 복사
    def copy_files(self, repo_dir: Path, repo_name: str, copy_list: list[str], transform_path: list[list[str]] = None):
        target_repo_dir = self.copy_dir
        transform_path = transform_path or []

        for rel_path in copy_list:
            src_file = (repo_dir / rel_path).resolve()
            dest_sub_path = Path(repo_name) / Path(rel_path)

            for src_prefix, dest_prefix in transform_path:
                src_parts = Path(src_prefix).parts
                dest_parts = Path(dest_prefix).parts
                parts = list(dest_sub_path.parts)

                for i in range(len(parts) - len(src_parts) + 1):
                    if parts[i:i + len(src_parts)] == list(src_parts):
                        parts[i:i + len(src_parts)] = list(dest_parts)
                        dest_sub_path = Path(*parts)
                        break

            dest_file = (target_repo_dir / dest_sub_path).resolve()

            if not src_file.exists():
                msg = f"⚠️ 존재하지 않는 파일: {src_file}"
                self.append_log(repo_name, msg)
                self.session_log(repo_name, msg)
                continue

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            msg = f"✅ 복사 완료: {dest_file}"
            self.append_log(repo_name, msg)
            self.session_log(repo_name, msg)
