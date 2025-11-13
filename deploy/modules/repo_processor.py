import subprocess
from pathlib import Path
from deploy.modules.git_manager import GitManager
from deploy.modules.file_manager import FileManager

class RepoProcessor:
    def __init__(self, git_manager: GitManager, file_manager: FileManager, repo_base_dir: str, ant_cmd: str):
        self.git = git_manager
        self.fm = file_manager
        self.repo_base_dir = Path(repo_base_dir).resolve()
        self.ant_cmd = ant_cmd  # config에서 전달
        self.backup_done = False

    def process_repo(self, repo_info: dict):
        repo_path = repo_info["name"]
        copy_list = repo_info.get("copy_list", [])
        transform_path = repo_info.get("transform_path", [])

        repo_name = Path(repo_path).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        print(f"\n🚀 처리 시작: {repo_name}")
        repo_dir = self.git.clone_or_pull(repo_path, self.repo_base_dir)

        # === Ant 빌드 실행 ===
        build_xml = repo_dir / "build.xml"
        if not build_xml.exists():
            msg = f"❌ build.xml 없음, 빌드 스킵: {repo_name}"
            print(msg)
            self.fm._write_log(repo_name, msg)
            return

        try:
            subprocess.run([self.ant_cmd], cwd=repo_dir, check=True)
            print(f"✅ 빌드 완료: {repo_name}")
            self.fm._write_log(repo_name, "빌드 성공")
        except FileNotFoundError:
            msg = f"❌ Ant 실행 파일을 찾을 수 없음: {self.ant_cmd}"
            print(msg)
            self.fm._write_log(repo_name, msg)
            return
        except subprocess.CalledProcessError as e:
            msg = f"❌ 빌드 실패: {e}"
            print(msg)
            self.fm._write_log(repo_name, msg)
            return

        # === copy_dir 전체 백업 (최초 1회) ===
        if copy_list and not self.backup_done:
            self.fm.backup_copy_target()
            self.backup_done = True

        # === build 폴더 기준 파일 체크 및 복사 ===
        build_dir = repo_dir / "build"
        exist_files, missing_files = self.fm.check_copy_files_exist(build_dir, copy_list)

        if missing_files:
            msg = f"⚠️ 존재하지 않는 파일 발견: {len(missing_files)}개"
            print(msg)
            print("[❌ 존재하지 않는 파일 목록]")
            for f in missing_files:
                print(f"   - {f}")
            self.fm._write_log(repo_name, msg + "\n" + "\n".join(missing_files))

        if exist_files:
            self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)
