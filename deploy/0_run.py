# run_all.py
import sys
import subprocess
from pathlib import Path


def run_script(script_path: Path, args: list[str]) -> None:
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    cmd = [sys.executable, str(script_path), *args]

    print("\n" + "=" * 60)
    print(f"RUN: {' '.join(cmd)}")
    print("=" * 60)

    # stdout/stderr를 그대로 현재 콘솔로 전달
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] {script_path.name} failed with code {result.returncode}")


def main():
    base_dir = Path(__file__).resolve().parent

    # 전달받은 인자(예: 0206, 20260206)를 그대로 다음 스크립트들에 전달
    passed_args = sys.argv[1:]  # 없으면 []

    # 실행 순서: 1_work.py -> 2_main.py -> 3_check.py
    scripts = ["1_work.py", "2_main.py", "3_check.py"]

    for s in scripts:
        run_script(base_dir / s, passed_args)

    print("\nAll done: 1_work.py -> 2_main.py -> 3_check.py")


if __name__ == "__main__":
    main()