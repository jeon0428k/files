import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    # Re-run this script with admin privileges, preserving all arguments
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",           # triggers UAC prompt
        sys.executable,    # python.exe
        params,            # script + args
        None,
        1
    )
    # If user cancels UAC, rc is typically <= 32
    sys.exit(0 if rc > 32 else 1)


def run_many_exes(exe_paths: list[str]) -> int:
    exit_code = 0

    for exe in exe_paths:
        exe = exe.strip().strip('"')  # tolerate quoted inputs

        if not exe:
            continue

        if not os.path.isabs(exe):
            exe = os.path.abspath(exe)

        if not os.path.exists(exe):
            print(f"[NOT FOUND] {exe}")
            exit_code = 1
            continue

        if not exe.lower().endswith(".exe"):
            print(f"[SKIP] Not an .exe: {exe}")
            exit_code = 1
            continue

        print(f"[RUN] {exe}")
        try:
            r = subprocess.run([exe], check=False)
            if r.returncode == 0:
                print(f"[OK]  {exe}")
            else:
                print(f"[FAIL] {exe} (exit code={r.returncode})")
                exit_code = 1
        except Exception as e:
            print(f"[ERROR] {exe} ({e})")
            exit_code = 1

    return exit_code


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage:")
        print('  python run_exes_as_admin.py "C:\\Path\\A.exe" "C:\\Path With Space\\B.exe"')
        return 2

    if not is_admin():
        relaunch_as_admin()
        return 0  # not reached

    exe_paths = sys.argv[1:]
    return run_many_exes(exe_paths)


if __name__ == "__main__":
    raise SystemExit(main())