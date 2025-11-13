import shutil
import subprocess
from pathlib import Path

class RepoProcessor:
    def __init__(self, git_manager, file_manager, repo_base_dir: str, ant_cmd: str):
        self.git = git_manager
        self.git.fm = file_manager  # Git 로그 기록용
        self.fm = file_manager
        self.repo_base_dir = Path(repo_base_dir).resolve()
        self.ant_cmd = ant_cmd

    def process_repo(self, repo_info: dict):
        repo_path = repo_info["name"]
        copy_list = repo_info.get("copy_list", [])
        transform_path = repo_info.get("transform_path", [])
        build_file = repo_info.get("build_file")
        git_mode = repo_info.get("git_mode", "pull")

        repo_name = Path(repo_path).name
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        # ================= backup (session log 생성 전) =================
        self.fm.backup_copy_target()

        # session log 시작
        self.fm.append_log(repo_name, f"🚀 처리 시작: {repo_name}")
        self.fm.session_log(repo_name, f"🚀 처리 시작: {repo_name}")

        # Git clone/pull
        repo_dir = self.git.clone_or_pull(repo_path, self.repo_base_dir, git_mode)

        # build_file 확인
        if not build_file:
            msg = f"❌ build_file 지정 없음. {repo_name} 처리 중단"
            self.fm.append_log(repo_name, msg)
            self.fm.session_log(repo_name, msg)
            return

        build_file_path = Path(build_file).resolve()
        if not build_file_path.exists():
            msg = f"❌ 지정된 build_file 없음: {build_file_path}"
            self.fm.append_log(repo_name, msg)
            self.fm.session_log(repo_name, msg)
            return

        # build_file 복사
        dest_build_file = repo_dir / build_file_path.name
        shutil.copy2(build_file_path, dest_build_file)
        msg = f"📄 build_file 복사 완료: {dest_build_file}"
        self.fm.append_log(repo_name, msg)
        self.fm.session_log(repo_name, msg)

        # Ant 빌드
        try:
            subprocess.run([self.ant_cmd, "-f", str(dest_build_file)], cwd=repo_dir, check=True)
            msg = "✅ 빌드 성공"
            self.fm.append_log(repo_name, msg)
            self.fm.session_log(repo_name, msg)
        except FileNotFoundError:
            msg = f"❌ Ant 실행 파일을 찾을 수 없음: {self.ant_cmd}"
            self.fm.append_log(repo_name, msg)
            self.fm.session_log(repo_name, msg)
            return
        except subprocess.CalledProcessError as e:
            msg = f"❌ 빌드 실패: {e}"
            self.fm.append_log(repo_name, msg)
            self.fm.session_log(repo_name, msg)
            return

        # build 폴더 기준 copy
        build_dir = repo_dir / "build"
        exist_files, missing_files = self.fm.check_copy_files_exist(build_dir, copy_list)

        if missing_files:
            msg = f"⚠️ 존재하지 않는 파일 발견: {len(missing_files)}개"
            print(msg)
            for f in missing_files:
                print(f"   - {f}")
            self.fm.append_log(repo_name, msg + "\n" + "\n".join(missing_files))
            self.fm.session_log(repo_name, msg + "\n" + "\n".join(missing_files))

        if exist_files:
            self.fm.copy_files(build_dir, repo_name, exist_files, transform_path)
