from deploy.modules.git_manager import GitManager
from deploy.modules.file_manager import FileManager


class RepoProcessor:
    def __init__(self, git_manager: GitManager, file_manager: FileManager, repo_base_dir: str):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = repo_base_dir
        self.backup_done = False  # copy_target 전체 백업 여부

    def process_repo(self, repo_info: dict):
        repo_name = repo_info["name"]
        copy_list = repo_info.get("copy_list")
        transform_path = repo_info.get("transform_path")

        print(f"\n🚀 처리 중: {repo_name}")
        repo_dir = self.git.clone_or_pull(repo_name, self.repo_base_dir)
        repo_folder_name = repo_dir.name

        if not copy_list:
            msg = f"⏩ Skip: {repo_name} (copy_list 없음)"
            print(msg)
            self.fm._write_log(repo_folder_name, msg)
            return

        # === 존재 여부 확인 ===
        exist_files, missing_files = self.fm.check_copy_files_exist(repo_dir, copy_list)

        if missing_files:
            print(f"⚠️ 일부 파일이 존재하지 않아 복사 작업을 중단합니다: {repo_name}")
            print("\n[✅ 존재하는 파일 목록]")
            for f in exist_files:
                print(f"   - {f}")
            print("\n[❌ 존재하지 않는 파일 목록]")
            for f in missing_files:
                print(f"   - {f}")

            # === 로그 추가: 존재하지 않는 파일 목록도 함께 기록 ===
            log_msg = f"❌ 복사 중단: 존재하지 않는 파일 {len(missing_files)}개 발견\n"
            log_msg += "\n".join([f"   - {f}" for f in missing_files])
            self.fm._write_log(repo_folder_name, log_msg)
            return  # 복사 중단

        # copy_target 전체 백업 (한 번만)
        if not self.backup_done:
            self.fm.backup_copy_target()
            self.backup_done = True

        # 실제 복사 진행
        self.fm.copy_files(repo_dir, repo_folder_name, copy_list, transform_path)
