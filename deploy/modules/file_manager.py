import shutil
from pathlib import Path
from datetime import datetime

class FileManager:
    def __init__(self, copy_base_dir: str, logs_base_dir: str):
        self.copy_base_dir = Path(copy_base_dir).resolve()
        self.backup_base = self.copy_base_dir.parent / "backup"
        self.backup_base.mkdir(parents=True, exist_ok=True)

        self.logs_base_dir = Path(logs_base_dir).resolve()
        self.logs_base_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self, repo_name: str, timestamped: bool = False) -> Path:
        """
        timestamped=True 면 copy 폴더에 시점별 로그 파일 생성
        """
        if timestamped:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return self.copy_base_dir / f"{timestamp}_{repo_name}.log"
        else:
            return self.logs_base_dir / f"{repo_name}.log"

    def _write_log(self, repo_name: str, message: str, timestamped: bool = False):
        log_file = self._get_log_file(repo_name, timestamped)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    def backup_copy_target(self):
        if self.copy_base_dir.exists() and any(self.copy_base_dir.iterdir()):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_base / f"{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)
            for item in self.copy_base_dir.iterdir():
                shutil.move(str(item), str(backup_path / item.name))
            print(f"📦 전체 백업 완료: {self.copy_base_dir} → {backup_path}")

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

    def copy_files(self, repo_dir: Path, repo_name: str, copy_list: list[str], transform_path: list[list[str]] = None):
        target_repo_dir = self.copy_base_dir
        transform_path = transform_path or []

        # 시점별 로그 파일 생성
        timestamped_log = True

        for rel_path in copy_list:
            src_file = (repo_dir / rel_path).resolve()
            dest_sub_path = Path(repo_name) / Path(rel_path)

            # transform_path 적용
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
                print(msg)
                self._write_log(repo_name, msg, timestamped=timestamped_log)
                continue

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            msg = f"✅ 복사 완료: {dest_file}"
            print(msg)
            self._write_log(repo_name, msg, timestamped=timestamped_log)
