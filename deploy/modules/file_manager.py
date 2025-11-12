import shutil
from pathlib import Path
from datetime import datetime

class FileManager:
    def __init__(self, copy_base_dir: str, log_base_dir: str):
        self.copy_base_dir = Path(copy_base_dir).resolve()
        self.backup_base = self.copy_base_dir.parent / "backup"
        self.backup_base.mkdir(parents=True, exist_ok=True)

        self.log_base_dir = Path(log_base_dir).resolve()
        self.log_base_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self, repo_name: str) -> Path:
        return self.log_base_dir / f"{repo_name}.log"

    def _write_log(self, repo_name: str, message: str):
        log_file = self._get_log_file(repo_name)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    def backup_if_exists(self, repo_name: str):
        target_dir = self.copy_base_dir / repo_name
        if target_dir.exists() and any(target_dir.iterdir()):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_base / f"{timestamp}_{repo_name}"  # YYYYMMDD_HHMMSS_(repository명)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target_dir), str(backup_path))
            self._write_log(repo_name, f"Backup: {target_dir} → {backup_path}")

    def copy_files(self, repo_dir: Path, repo_name: str, copy_list: list[str], transform_path: dict[str,str] = None):
        target_repo_dir = self.copy_base_dir / repo_name
        transform_path = transform_path or {}

        for rel_path in copy_list:
            src_file = (repo_dir / rel_path).resolve()
            
            # 변환 경로 적용: 정의된 것만 변환
            dest_sub_path = Path(rel_path)
            for src_prefix, dest_prefix in transform_path.items():
                if rel_path.startswith(src_prefix):
                    suffix = Path(rel_path).relative_to(src_prefix)
                    dest_sub_path = Path(dest_prefix) / suffix
                    break  # 첫 번째 매칭만 적용

            dest_file = (target_repo_dir / dest_sub_path).resolve()

            if not src_file.exists():
                msg = f"⚠️ 존재하지 않는 파일: {src_file}"
                print(msg)
                self._write_log(repo_name, msg)
                continue

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            msg = f"✅ 복사 완료: {dest_file}"
            print(msg)
            self._write_log(repo_name, msg)