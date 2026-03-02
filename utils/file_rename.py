import os
import fnmatch
import shutil
from pathlib import Path
from datetime import datetime

# ============================================================
# 사용자 설정 영역
# ============================================================

TARGET_DIR = r"D:\deploy\test\exam"

REPLACE_PATTERN = [
    ("*.java", "*.class"),
    ("*.jsp", "*.html"),
]

# ============================================================
# 내부 엔진
# ============================================================

def apply_replace(name: str) -> str:
    """
    파일/디렉토리 이름에 대해 모든 REPLACE_PATTERN 을 순차적으로 적용한다.
    """
    new_name = name

    for src, dst in REPLACE_PATTERN:
        if fnmatch.fnmatch(new_name, src):
            # glob 형태 replace ( * 부분 유지 )
            core = src.replace("*", "")
            star_part = new_name.replace(core, "")
            new_name = dst.replace("*", star_part)
        else:
            # 일반 문자열 replace
            new_name = new_name.replace(src, dst)

    return new_name


def backup_target_dir(target: Path) -> Path:
    """
    TARGET_DIR 부모 경로 밑에
    backup/{디렉토리명}_YYYYMMDD_HHMMSS 구조로 전체 백업
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    parent = target.parent                      # D:\deploy\test
    backup_root = parent / "backup"             # D:\deploy\test\backup
    backup_root.mkdir(exist_ok=True)

    backup_dir = backup_root / f"{target.name}_{ts}"

    print(f"[BACKUP] {target} -> {backup_dir}")
    shutil.copytree(target, backup_dir)

    return backup_dir


def rename_tree(root: Path):
    """
    root 이하 모든 파일/디렉토리를 규칙에 따라 rename
    """
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):

        old = path.name
        new = apply_replace(old)

        if old == new:
            continue

        new_path = path.with_name(new)

        if new_path.exists():
            print(f"[SKIP] {new_path} already exists")
            continue

        print(f"[RENAME] {path} -> {new_path}")
        path.rename(new_path)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    root = Path(TARGET_DIR)

    if not root.exists():
        print("TARGET_DIR not found")
        exit(1)

    # 1. 전체 백업
    backup_target_dir(root)

    # 2. rename 실행
    rename_tree(root)

    print("\nDONE")
