import shutil
from pathlib import Path
from datetime import datetime
from threading import Lock
from collections import Counter


class FileManager:
    def __init__(self, copy_dir: str, logs_dir: str, back_dir: str):
        # 결과물 copy 대상 디렉토리
        self.copy_dir = Path(copy_dir).resolve()
        # 전체 로그 디렉토리
        self.logs_dir = Path(logs_dir).resolve()
        # copy 폴더 백업 디렉토리
        self.backup_dir = Path(back_dir).resolve()

        for d in [self.copy_dir, self.logs_dir, self.backup_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 세션 로그는 ALL 모드일 때만 활성화
        # 세션 로그 파일 위치: copy_dir / {repo_name}.log
        self.session_logs = {}
        self.enable_session_log = False

        # copy 폴더 백업 1회만 수행 제어
        self.backup_done = False
        self.lock = Lock()

    # -----------------------------------------------------
    # 전체 로그 기록 (항상 append)
    # -----------------------------------------------------
    def append_log(self, repo_name: str, message: str):
        """
        전체 로그:
          - logs_dir / {repo_name}.log 에 append 방식으로 기록
        """
        file = self.logs_dir / f"{repo_name}.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")

    # -----------------------------------------------------
    # 세션 로그 기록 (ALL 모드일 때만 사용)
    # -----------------------------------------------------
    def session_log(self, repo_name: str, message: str):
        """
        세션 로그:
          - enable_session_log == True(= execute == 'all') 인 경우에만 기록
          - copy_dir / {repo_name}.log 에 기록
          - 전체 로그와 동일한 메시지가 기록되도록 dual_log 에서 호출
        """
        if not self.enable_session_log:
            return
        if repo_name not in self.session_logs:
            self.session_logs[repo_name] = self.copy_dir / f"{repo_name}.log"

        file = self.session_logs[repo_name]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")

    # -----------------------------------------------------
    # 전체 로그 + (필요 시) 세션 로그 + 콘솔 동시 출력
    # -----------------------------------------------------
    def dual_log(self, repo_name: str, message: str, console: bool = True):
        """
        전체 로그와 세션 로그를 동일한 내용으로 기록하고,
        콘솔에도 동일 메시지를 출력하는 공통 함수.

        - 전체 로그: 항상 append
        - 세션 로그: execute == 'all' 인 경우에만 기록
        - 콘솔: 기본적으로 출력 (console=False 로 끌 수 있음)
        """
        # 전체 로그 기록
        self.append_log(repo_name, message)

        # 세션 로그 기록 (ALL 모드일 때만)
        if self.enable_session_log:
            self.session_log(repo_name, message)

        # 콘솔 출력
        if console:
            print(f"[{repo_name}] {message}")

    # -----------------------------------------------------
    # copy 폴더 백업
    # -----------------------------------------------------
    def backup_copy_target(self):
        """
        copy_dir 내 파일이 존재할 경우, backup_dir/타임스탬프 아래로
        모든 항목을 이동(백업)한다. 한 번만 수행된다.
        """
        with self.lock:
            if self.backup_done:
                return

            if any(self.copy_dir.iterdir()):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.backup_dir / ts
                backup_path.mkdir(parents=True, exist_ok=True)

                for item in self.copy_dir.iterdir():
                    shutil.move(str(item), str(backup_path / item.name))

                # 백업 로그는 repo 단위가 아니므로 콘솔 출력만 수행
                print(f"Copy folder backup completed → {backup_path}")

            self.backup_done = True

    # -----------------------------------------------------
    # 파일 존재 여부 체크
    # -----------------------------------------------------
    def check_copy_files_exist(self, repo_dir: Path, copy_list: list[str]):
        """
        build 디렉토리 기준으로 copy_list 내 파일의 존재 여부를 체크.
        """
        exist_files = []
        missing_files = []

        for rel in copy_list:
            if (repo_dir / rel).exists():
                exist_files.append(rel)
            else:
                missing_files.append(rel)

        return exist_files, missing_files

    # -----------------------------------------------------
    # 파일 복사 (중복 목적지 방지 적용)
    # -----------------------------------------------------
    def copy_files(self, repo_dir: Path, repo_name: str,
                   copy_list: list[str], transform_path=None):

        transform_path = transform_path or []
        copied_dest_set = set()

        for rel in copy_list:
            src = (repo_dir / rel).resolve()
            if not src.exists():
                continue

            # 기본 목적지 경로 생성
            dest_sub = Path(repo_name) / Path(rel)

            # transform_path 적용
            for src_prefix, dest_prefix in transform_path:
                sp = Path(src_prefix).parts
                dp = Path(dest_prefix).parts
                parts = list(dest_sub.parts)

                for i in range(len(parts) - len(sp) + 1):
                    if parts[i:i + len(sp)] == list(sp):
                        parts[i:i + len(sp)] = dp
                        dest_sub = Path(*parts)
                        break

            dest = (self.copy_dir / dest_sub).resolve()

            # 목적지 중복 차단
            key = str(dest)
            if key in copied_dest_set:
                continue
            copied_dest_set.add(key)

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

            # 전체 로그 + 세션 로그 + 콘솔 동일 메시지
            self.dual_log(repo_name, f"Copy completed: {dest}")

    # -----------------------------------------------------
    # 요약 + 상세 목록 출력
    # -----------------------------------------------------
    def log_file_check_summary(
        self,
        repo_name,
        exist_files,
        missing_files,
        raw_total,
        unique_total,
        exist_raw,
        exist_unique,
        missing_raw,
        missing_unique,
        raw_count_map,
    ):
        """
        파일 존재 여부 체크 결과를
        - 전체 로그
        - (ALL 모드 시) 세션 로그
        - 콘솔
        에 기록하는 함수.
        """

        exist_counter = Counter(exist_files)
        missing_counter = Counter(missing_files)

        # 전체 로그 + 세션 로그에 상세 파일 목록 기록
        for p in sorted(exist_counter.keys()):
            raw_cnt = raw_count_map.get(p, 1)
            msg = f"[O] {p},{raw_cnt}"
            # 전체 로그와 세션 로그에 동일하게 기록 (콘솔 출력은 하지 않음)
            self.append_log(repo_name, msg)
            if self.enable_session_log:
                self.session_log(repo_name, msg)

        for p in sorted(missing_counter.keys()):
            raw_cnt = raw_count_map.get(p, 1)
            msg = f"[X] {p},{raw_cnt}"
            # 전체 로그와 세션 로그에 동일하게 기록 (콘솔 출력은 하지 않음)
            self.append_log(repo_name, msg)
            if self.enable_session_log:
                self.session_log(repo_name, msg)

        # 콘솔에는 미존재 파일만 출력
        if missing_counter:
            for p in sorted(missing_counter.keys()):
                raw_cnt = raw_count_map.get(p, 1)
                print(f"[{repo_name}] [X] {p},{raw_cnt}")

        # summary 메시지 생성
        summary = (
            f"File check summary → total: {raw_total}({unique_total}), "
            f"exists: {exist_raw}({exist_unique}), "
            f"missing: {missing_raw}({missing_unique})"
        )

        # summary 는 dual_log 로 처리
        # → 전체 로그, 세션 로그(ALL 모드), 콘솔에 동일한 내용 출력
        self.dual_log(repo_name, summary)
