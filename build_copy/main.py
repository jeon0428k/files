import sys
import yaml
import shutil
from pathlib import Path
from datetime import datetime

CONFIG_FILE = "./config/config.yml"


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_worklist(worklist_file: str) -> list[Path]:
    p = Path(worklist_file)
    if not p.exists():
        print(f"> {now_str()}")
        print(f"worklist file not found: {p.resolve()}")
        sys.exit(2)

    items = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(Path(s).resolve())
    return items


def main():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    print(f"> {now_str()}\n")

    copy_root = Path(config["copy_dir"])
    is_worklist = bool(config.get("is_worklist", False))
    worklist_file = config.get("worklist_file")

    if is_worklist and not worklist_file:
        print("worklist_file is required when is_worklist = true")
        sys.exit(2)

    repositories = config.get("repositories", []) or []
    repo_base_map = {r["name"]: Path(r["path"]).resolve() for r in repositories}

    # --- worklist 분류
    repo_work_map = {}
    unmapped = []

    if is_worklist:
        for p in read_worklist(worklist_file):
            mapped = False
            for repo in repositories:
                base = repo_base_map[repo["name"]]
                try:
                    p.relative_to(base)
                    repo_work_map.setdefault(repo["name"], []).append(p)
                    mapped = True
                    break
                except Exception:
                    pass
            if not mapped:
                unmapped.append(p)

    # --- repo 처리
    for repo in repositories:
        repo_name = repo["name"]
        execute = bool(repo.get("execute", False))
        repo_dir = repo["dir"]
        base_path = repo_base_map[repo_name]
        repo_root = copy_root / repo_name

        print(f"=================================")
        print(f"[{repo_name}]")
        print("---------------------------------")

        if not execute:
            print("execution disabled")
            print(f"=================================\n")
            continue

        targets = repo_work_map.get(repo_name, []) if is_worklist else [
            Path(s).resolve() for s in (repo.get("copy_list", []) or [])
        ]

        if not targets:
            print("empty")
            print(f"=================================\n")
            continue

        if repo_root.exists():
            print(f"remove dir: {repo_root}")
            shutil.rmtree(repo_root)

        target_root = repo_root / repo_dir
        target_root.mkdir(parents=True, exist_ok=True)

        print(f"target root: {base_path}")
        print(f"copy root: {target_root}")
        print("----------")

        # --- 결과를 모아서 정렬 출력
        result_logs = []

        for src_path in targets:
            # 존재 안함
            if not src_path.exists():
                result_logs.append(("X", str(src_path), None))
                continue

            # base path 기준 상대경로 계산
            try:
                relative_path = src_path.relative_to(base_path)
            except Exception as e:
                result_logs.append(("X", str(src_path), str(e)))
                continue

            try:
                dest_path = target_root / relative_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(src_path, dest_path)
                result_logs.append(("O", str(src_path), str(dest_path)))
            except Exception as e:
                result_logs.append(("X", str(src_path), str(e)))

        # 경로 기준 정렬 후 출력
        for status, src, extra in sorted(result_logs, key=lambda x: x[1]):
            if status == "O":
                print(f"[O] {src} -> {extra}")
            else:
                print(f"[X] {src}")
                if extra:
                    print(f"    : {extra}")

        print(f"=================================\n")

    # --- UNMAPPED 감사 출력 (정렬 포함)
    if is_worklist and unmapped:
        print("=================================")
        print("[UNMAPPED]")
        print("---------------------------------")
        for p in sorted(unmapped, key=lambda x: str(x)):
            print(f"[X] {p}")
        print("=================================")


if __name__ == "__main__":
    main()
