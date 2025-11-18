import shutil
import subprocess
from pathlib import Path


class RepoProcessor:
    def __init__(self, git_manager, file_manager, repo_base_dir, ant_cmd, global_branch):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = Path(repo_base_dir)
        self.ant_cmd = ant_cmd
        self.global_branch = global_branch  # fallback 용

    # ---------------------------------------------------------
    # repository 단위 전체 실행
    # ---------------------------------------------------------
    def process_repo(self, repo_info: dict):
        repo_path = repo_info["name"]
        repo_name = Path(repo_path).stem

        exec_list = repo_info.get("execute", [])
        git_mode = repo_info.get("git_mode", "pull")
        repo_branch = repo_info.get("branch")  # repository 전용 branch

        build_file = repo_info.get("build_file")
        transform_path = repo_info.get("transform_path", [])

        unique_copy_list = repo_info.get("unique_copy_list", [])
        raw_copy_list = repo_info.get("raw_copy_list", [])
        copy_count_map = repo_info.get("copy_count_map", {})

        # -----------------------------------------------------
        # stop 우선 실행: 해당 repo는 즉시 스킵
        # -----------------------------------------------------
        if "stop" in exec_list:
            self.fm.dual_log(repo_name, "Execution skipped (stop found)")
            return

        # -----------------------------------------------------
        # ALL 있을 경우 → 기존 full pipeline 수행
        # -----------------------------------------------------
        if "all" in exec_list:
            self.process_all(
                repo_path, repo_name, git_mode, repo_branch,
                build_file, transform_path,
                unique_copy_list, raw_copy_list, copy_count_map
            )
            return

        # -----------------------------------------------------
        # 개별 실행 모드: git → build → copy → check 순서로 판단
        # -----------------------------------------------------
        self.fm.enable_session_log = True
        self.fm.dual_log(repo_name, f"Execution mode (list): {exec_list}")

        repo_dir = None

        # -------------------- Git --------------------
        if "git" in exec_list:
            repo_dir = self.git.clone_or_pull(
                repo_path, self.repo_base_dir,
                git_mode, branch=repo_branch
            )

            # build_file repo 내부로 복사
            if build_file:
                bf = Path(build_file).resolve()
                if bf.exists():
                    dest = repo_dir / bf.name
                    shutil.copy2(bf, dest)
                    self.fm.dual_log(repo_name, f"Build file copied: {dest}")

        # Git을 실행하지 않은 경우 repo_dir 설정
        repo_dir = repo_dir or (self.repo_base_dir / repo_name)

        # -------------------- Build --------------------
        if "build" in exec_list:
            self.run_build(repo_name, repo_dir, build_file)

        # -------------------- Build 디렉토리 체크 --------------------
        build_dir = repo_dir / "build"

        # 🔥 build_dir 존재하지 않을 경우 로그 및 콘솔 출력
        if not build_dir.exists():
            msg = f"Build directory not found: {build_dir}"
            self.fm.dual_log(repo_name, msg)  # 콘솔 + 전체로그 + 세션로그
            return

        # -------------------- File 존재 체크 --------------------
        exist_files, missing_files = self.fm.check_copy_files_exist(build_dir, unique_copy_list)

        # -------------------- Copy --------------------
        if "copy" in exec_list:
            self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)

        # -------------------- Check --------------------
        if "check" in exec_list:
            self.fm.log_file_check_summary(
                repo_name, exist_files, missing_files,
                len(raw_copy_list), len(unique_copy_list),
                sum(copy_count_map.get(x, 0) for x in exist_files),
                len(exist_files),
                sum(copy_count_map.get(x, 0) for x in missing_files),
                len(missing_files),
                copy_count_map
            )

    # ---------------------------------------------------------
    # 공통 Build 실행 함수
    # ---------------------------------------------------------
    def run_build(self, repo_name, repo_dir, build_file):
        if not build_file:
            self.fm.dual_log(repo_name, "Build file missing → cannot execute build")
            return

        bf_path = repo_dir / Path(build_file).name

        try:
            subprocess.run([self.ant_cmd, "-f", str(bf_path)], cwd=repo_dir, check=True)
            self.fm.dual_log(repo_name, "Build succeeded")
        except Exception as e:
            self.fm.dual_log(repo_name, f"Build failed: {e}")

    # ---------------------------------------------------------
    # ALL 모드: 기존 full pipeline 처리
    # ---------------------------------------------------------
    def process_all(self, repo_path, repo_name, git_mode, repo_branch,
                    build_file, transform_path,
                    unique_copy_list, raw_copy_list, copy_count_map):

        # 세션 로그 활성화
        self.fm.enable_session_log = True

        # copy_dir 백업 (한 번만 수행)
        self.fm.backup_copy_target()

        self.fm.dual_log(repo_name, "Execution mode: all")

        # -------------------- Git 단계 --------------------
        repo_dir = self.git.clone_or_pull(
            repo_path, self.repo_base_dir,
            git_mode, branch=repo_branch
        )

        # build_file 복사
        if build_file:
            bf = Path(build_file).resolve()
            if bf.exists():
                dest = repo_dir / bf.name
                shutil.copy2(bf, dest)
                self.fm.dual_log(repo_name, f"Build file copied: {dest}")

        # -------------------- Build 단계 --------------------
        self.run_build(repo_name, repo_dir, build_file)

        # -------------------- Build 디렉토리 체크 --------------------
        build_dir = repo_dir / "build"

        # 🔥 build_dir 존재하지 않을 경우 로그 및 콘솔 출력
        if not build_dir.exists():
            msg = f"Build directory not found: {build_dir}"
            self.fm.dual_log(repo_name, msg)
            return  # ALL 모드라도 copy/check 불가 → 종료

        # -------------------- File 존재 체크 --------------------
        exist_files, missing_files = self.fm.check_copy_files_exist(build_dir, unique_copy_list)

        # -------------------- Copy --------------------
        self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)

        # -------------------- Summary 출력 --------------------
        self.fm.log_file_check_summary(
            repo_name, exist_files, missing_files,
            len(raw_copy_list), len(unique_copy_list),
            sum(copy_count_map.get(x, 0) for x in exist_files),
            len(exist_files),
            sum(copy_count_map.get(x, 0) for x in missing_files),
            len(missing_files),
            copy_count_map
        )
