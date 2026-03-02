import subprocess
from pathlib import Path


def run_program(exe_path: str, args=None, background=True):
    exe = Path(exe_path)
    if not exe.exists():
        raise FileNotFoundError(f"Not found: {exe}")

    cmd = [str(exe)]
    if args:
        cmd.extend(args)

    kwargs = {}
    if background:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return subprocess.Popen(cmd, **kwargs)


# 사용 예
run_program(
    r"C:\Windows\System32\notepad.exe",
    args=[r"C:\temp\test.txt"]
)
