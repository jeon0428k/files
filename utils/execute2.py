import subprocess

exe_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

subprocess.Popen(
    [exe_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW
)