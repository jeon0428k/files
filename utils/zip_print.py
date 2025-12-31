import yaml
import zipfile
from pathlib import Path
from datetime import datetime

CONFIG_FILE = "./config/zip.config.yml"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if "zip_file" not in cfg:
        raise KeyError("config에 zip_file 이 없습니다.")
    return cfg


def zipinfo_dt(zi: zipfile.ZipInfo) -> datetime:
    y, mo, d, h, mi, s = zi.date_time
    return datetime(y, mo, d, h, mi, s)


def to_mb(size: int) -> float:
    return round(size / (1024 * 1024), 2)


# 🔽 추가: 현재 시간과의 차이를 HH:MM:SS 로 변환
def diff_hms(dt: datetime) -> str:
    diff = abs(datetime.now() - dt)
    sec = int(diff.total_seconds())
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02}:{m:02}:{s:02}"


def main() -> int:
    print(f"> {now_str()}\n")

    cfg = load_config()
    zip_path = Path(str(cfg["zip_file"]))

    print_line = int(cfg.get("print_line", 20))
    if print_line < 1:
        print_line = 1

    if not zip_path.exists():
        print(f"[ERROR] zip_file not found: {zip_path}")
        return 2

    items: list[tuple[datetime, str, zipfile.ZipInfo]] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for zi in zf.infolist():
            if zi.filename.endswith("/"):
                continue
            items.append((zipinfo_dt(zi), zi.filename, zi))

    # 시간 내림차순, 파일명 오름차순
    items.sort(key=lambda x: (-x[0].timestamp(), x[1]))

    print(f"[ZIP] {zip_path}")
    print(f"[COUNT] total_files={len(items)}, print_line={print_line}\n")

    # 🔽 출력 형식 변경
    for dt, name, zi in items[:print_line]:
        print(f"({diff_hms(dt)}) {dt.strftime('%Y-%m-%d %H:%M:%S')} | {to_mb(zi.file_size):6.2f} MB | {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
