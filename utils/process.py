import ctypes
from ctypes import wintypes
import subprocess

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# =====================
# Helper functions
# =====================
def enum_windows():
    """모든 윈도우 핸들을 반환"""
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_void_p)
    hwnds = []

    def foreach(hwnd, lParam):
        hwnds.append(hwnd)
        return True

    EnumWindows(EnumWindowsProc(foreach), 0)
    return hwnds

def get_pid_from_hwnd(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def get_exe_path(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    hProcess = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hProcess:
        return None
    buffer = ctypes.create_unicode_buffer(260)
    size = wintypes.DWORD(260)
    psapi.GetModuleFileNameExW(hProcess, 0, buffer, size)
    kernel32.CloseHandle(hProcess)
    return buffer.value

def is_process_alive(pid):
    """프로세스가 살아있는지 체크"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True

# =====================
# 트레이 프로세스 추출
# =====================
def get_tray_processes():
    tray_processes = {}
    for hwnd in enum_windows():
        if user32.IsWindowVisible(hwnd):
            pid = get_pid_from_hwnd(hwnd)
            exe = get_exe_path(pid)
            if exe:
                tray_processes[pid] = exe
    return tray_processes

# =====================
# 전체 프로세스 추출
# =====================
def get_all_processes():
    result = subprocess.run(["tasklist", "/FO", "CSV"], capture_output=True, text=True)
    lines = result.stdout.splitlines()
    processes = []
    for line in lines[1:]:
        cols = [c.strip('"') for c in line.split('","')]
        if len(cols) >= 5:
            processes.append({
                "name": cols[0],
                "pid": int(cols[1]),
                "mem": cols[4],
            })
    return processes

# =====================
# 메인
# =====================
def main():
    tray = get_tray_processes()
    all_procs = get_all_processes()

    # 4가지 그룹
    tray_running = []
    tray_not_running = []
    normal_running = []
    normal_not_running = []

    for p in all_procs:
        pid = p['pid']
        alive = is_process_alive(pid)
        status = "RUNNING" if alive else "NOT RUNNING"
        exe_path = tray.get(pid, "N/A") if pid in tray else "N/A"

        if pid in tray:
            if alive:
                tray_running.append(f"[TRAY][RUNNING] {p['name']} (PID={pid}, MEM={p['mem']}, PATH={exe_path})")
            else:
                tray_not_running.append(f"[TRAY][NOT RUNNING] {p['name']} (PID={pid}, MEM={p['mem']}, PATH={exe_path})")
        else:
            if alive:
                normal_running.append(f"[NORMAL][RUNNING] {p['name']} (PID={pid}, MEM={p['mem']})")
            else:
                normal_not_running.append(f"[NORMAL][NOT RUNNING] {p['name']} (PID={pid}, MEM={p['mem']})")

    print("=== 트레이 프로세스 (실행 중) ===")
    print("\n".join(tray_running) if tray_running else "없음")

    print("\n=== 트레이 프로세스 (실행 안 됨) ===")
    print("\n".join(tray_not_running) if tray_not_running else "없음")

    print("\n=== 일반 프로세스 (실행 중) ===")
    print("\n".join(normal_running) if normal_running else "없음")

    print("\n=== 일반 프로세스 (실행 안 됨) ===")
    print("\n".join(normal_not_running) if normal_not_running else "없음")


if __name__ == "__main__":
    main()
