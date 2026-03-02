import subprocess

exe_path = r"C:\Windows\System32\notepad.exe"

subprocess.run([
    "powershell",
    "-Command",
    f'Start-Process "{exe_path}" -Verb RunAs'
])
