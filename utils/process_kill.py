import sys
import psutil

def kill_process_by_name(proc_name: str) -> bool:
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.info['name']
            if name and name.lower() == proc_name.lower():
                proc.kill()
                print(f"[KILLED] {proc_name} (pid={proc.pid})")
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed


def main():
    if len(sys.argv) < 2:
        print("Usage: python tray_kill.py <process1.exe> <process2.exe> ...")
        sys.exit(1)

    targets = sys.argv[1:]
    print(f"[TARGETS] {', '.join(targets)}")

    for proc_name in targets:
        found = kill_process_by_name(proc_name)
        if not found:
            print(f"[NOT FOUND] {proc_name}")


if __name__ == "__main__":
    main()