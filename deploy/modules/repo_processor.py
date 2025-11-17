import shutil
import subprocess
from pathlib import Path


class RepoProcessor:
    def __init__(self, git_manager, file_manager, repo_base_dir, ant_cmd):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = Path(repo_base_dir)
        self.ant_cmd = ant_cmd

    def process_repo(self, repo_info: dict):
        repo_path = repo_info["name"]
        repo_name = Path(repo_path).stem

        execute = repo_info.get("execute", "all").lower()
        git_mode = repo_info.get("git_mode", "pull")
        build_file = repo_info.get("build_file")
        transform_path = repo_info.get("transform_path", [])

        unique_copy_list = repo_info.get("unique_copy_list", [])
        raw_copy_list = repo_info.get("raw_copy_list", [])
        copy_count_map = repo_info.get("copy_count_map", {})

        # ALL 모드일 때만 세션 로그 저장
        # git/build/copy/check/stop 모드에서는 세션 로그가 생성되지 않음
        self.fm.enable_session_log = (execute == "all")

        # copy_dir 백업 (최초 1회)
        self.fm.backup_copy_target()

        # 실행 모드 출력 (전체로그 + 세션로그(ALL 모드) + 콘솔)
        mode_msg = f"Execution mode: {execute}"
        self.fm.dual_log(repo_name, mode_msg)

        # -------------------- Git 단계 --------------------
        if execute in ["all", "git"]:
            repo_dir = self.git.clone_or_pull(repo_path, self.repo_base_dir, git_mode)

            # build_file 복사
            if build_file:
                bf = Path(build_file).resolve()
                if bf.exists():
                    dest = repo_dir / bf.name
                    shutil.copy2(bf, dest)

                    self.fm.dual_log(repo_name, f"Build file copied: {dest}")

            if execute == "git":
                return

        # Git 단계 후 repo_dir 재설정
        repo_dir = self.repo_base_dir / repo_name

        # -------------------- Build 단계 --------------------
        if execute in ["all", "build"]:
            if not build_file:
                self.fm.dual_log(repo_name, "Build file missing → cannot execute build")
                return

            bf_path = repo_dir / Path(build_file).name

            try:
                subprocess.run([self.ant_cmd, "-f", str(bf_path)], cwd=repo_dir, check=True)
                self.fm.dual_log(repo_name, "Build succeeded")
            except Exception as e:
                self.fm.dual_log(repo_name, f"Build failed: {e}")
                return

            if execute == "build":
                return

        # -------------------- 파일 존재 여부 체크 --------------------
        build_dir = repo_dir / "build"
        exist_files, missing_files = self.fm.check_copy_files_exist(build_dir, unique_copy_list)

        raw_total = len(raw_copy_list)
        unique_total = len(unique_copy_list)

        exist_unique = len(exist_files)
        missing_unique = len(missing_files)

        exist_raw = sum(copy_count_map.get(x, 0) for x in exist_files)
        missing_raw = sum(copy_count_map.get(x, 0) for x in missing_files)

        # -------------------- copy 단계 --------------------
        if execute == "copy":
            self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)

            self.fm.log_file_check_summary(
                repo_name, exist_files, missing_files,
                raw_total, unique_total,
                exist_raw, exist_unique,
                missing_raw, missing_unique,
                copy_count_map
            )
            return

        # -------------------- check 단계 --------------------
        if execute == "check":
            self.fm.log_file_check_summary(
                repo_name, exist_files, missing_files,
                raw_total, unique_total,
                exist_raw, exist_unique,
                missing_raw, missing_unique,
                copy_count_map
            )
            return

        # -------------------- all 단계 --------------------
        if execute == "all":
            # 존재하는 파일만 copy 수행
            self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)

            # 파일 체크 결과 요약/상세 로그
            self.fm.log_file_check_summary(
                repo_name, exist_files, missing_files,
                raw_total, unique_total,
                exist_raw, exist_unique,
                missing_raw, missing_unique,
                copy_count_map
            )
            return
