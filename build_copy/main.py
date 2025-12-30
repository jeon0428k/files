import yaml
import shutil
from pathlib import Path
from datetime import datetime

CONFIG_FILE = "./config/config.yml"


def main():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    copy_root = Path(config["copy_dir"])

    for repo in config["repositories"]:
        repo_name = repo["name"]
        execute = repo.get("execute", True)   # 기본 true
        repo_dir = repo["dir"]
        base_path = Path(repo["path"]).resolve()
        copy_list = repo["copy_list"]

        repo_root = copy_root / repo_name

        print(f"> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"===== [{repo_name}] start =====")

        if not execute:
            print("execution disabled")
            print(f"===== [{repo_name}] end =====\n")
            continue

        if repo_root.exists():
            print(f"remove dir: {repo_root}")
            shutil.rmtree(repo_root)

        target_root = repo_root / repo_dir
        target_root.mkdir(parents=True, exist_ok=True)

        print(f"target root: {base_path}")
        print(f"copy root: {repo_root} ({repo_dir})")
        print("-----")

        for src in copy_list:
            src_path = Path(src).resolve()
            exist_flag = "O" if src_path.exists() else "X"

            if not src_path.exists():
                print(f"[X]({exist_flag}) {src_path}")
                continue

            try:
                relative_path = src_path.relative_to(base_path)
            except ValueError:
                print(f"[X]({exist_flag}) {src_path}")
                continue

            dest_path = target_root / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src_path, dest_path)
            print(f"[O] {src_path} -> {dest_path}")

        print(f"===== [{repo_name}] end =====\n")


if __name__ == "__main__":
    main()
