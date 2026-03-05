import ctypes
import os
import subprocess
import sys
import time

# If True, retry on FAIL/ERROR
is_recursive_run = False

# Retry options (used only when is_recursive_run is True)
retry_interval = 1.0  # seconds
max_retry = 3         # max retry count per exe (0 or negative => infinite)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1
    )
    sys.exit(0 if rc > 32 else 1)


def _should_retry(current_retry_count: int) -> bool:
    # current_retry_count: retries already performed
    if not is_recursive_run:
        return False
    if 0 < max_retry <= current_retry_count:
        return False
    return True


def _sleep_between_retries() -> None:
    if retry_interval and retry_interval > 0:
        time.sleep(retry_interval)


def _normalize_exe_path(exe: str) -> str:
    exe = exe.strip().strip('"')
    if exe and not os.path.isabs(exe):
        exe = os.path.abspath(exe)
    return exe


def _validate_exe_path(exe: str) -> tuple[bool, str | None]:
    if not exe:
        return False, None

    if not os.path.exists(exe):
        return False, f"[NOT FOUND] {exe}"

    if not exe.lower().endswith(".exe"):
        return False, f"[SKIP] Not an .exe: {exe}"

    return True, None


def run_one_exe_with_retry(exe: str) -> tuple[bool, str | None]:
    """
    Returns (success, last_error_type)
      - success: True if exe eventually returns 0
      - last_error_type: "FAIL" | "ERROR" | None
    """
    retries = 0
    last_error_type: str | None = None

    while True:
        print(f"[RUN] {exe}")
        try:
            r = subprocess.run([exe], check=False)
            if r.returncode == 0:
                print(f"[OK]  {exe}")
                return True, None

            print(f"[FAIL] {exe} (exit code={r.returncode})")
            last_error_type = "FAIL"

        except Exception as e:
            print(f"[ERROR] {exe} ({e})")
            last_error_type = "ERROR"

        if not _should_retry(retries):
            if is_recursive_run and 0 < max_retry <= retries:
                print(f"[GIVE UP] {exe} (retries={retries}/{max_retry})")
            return False, last_error_type

        retries += 1
        _sleep_between_retries()


def run_many_exes(exe_paths: list[str]) -> int:
    exit_code = 0

    for raw in exe_paths:
        exe = _normalize_exe_path(raw)
        ok, msg = _validate_exe_path(exe)
        if not ok:
            if msg:
                print(msg)
                exit_code = 1
            continue

        success, _ = run_one_exe_with_retry(exe)
        if not success:
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