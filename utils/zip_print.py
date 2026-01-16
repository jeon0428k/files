import yaml
import zipfile
from pathlib import Path
from datetime import datetime

CONFIG_FILE = "./config/zip_print.config.yml"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # zip_files(리스트) 기준 적용 (문자열이면 리스트로 호환)
    if "zip_files" not in cfg:
        raise KeyError("config에 zip_files 가 없습니다.")

    zip_files = cfg.get("zip_files")
    if isinstance(zip_files, str):
        zip_files = [zip_files]
    if not isinstance(zip_files, list):
        raise ValueError("config zip_files must be a list (or a string)")

    cfg["zip_files"] = zip_files

    # 추가 옵션 (없으면 기본값)
    cfg["print_src"] = bool(cfg.get("print_src", False))
    cfg["filelist"] = cfg.get("filelist", "")

    return cfg


def zipinfo_dt(zi: zipfile.ZipInfo) -> datetime:
    y, mo, d, h, mi, s = zi.date_time
    return datetime(y, mo, d, h, mi, s)


def to_mb(size: int) -> float:
    return round(size / (1024 * 1024), 2)


def diff_hms(dt: datetime) -> str:
    diff = abs(datetime.now() - dt)
    total_sec = int(diff.total_seconds())

    days = total_sec // 86400
    h = (total_sec % 86400) // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60

    return f"{days:03}d {h:02}:{m:02}:{s:02}"


def read_filelist(filelist_path: str) -> list[str]:
    """
    filelist 파일에서 zip 내부 경로 목록을 읽는다.
    - 빈 줄, 주석(#) 무시
    - 앞뒤 공백 제거
    """
    if not filelist_path:
        return []

    p = Path(filelist_path)
    if not p.exists():
        print(f"[WARN] filelist not found: {p}")
        return []

    items: list[str] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s)
    return items


def print_zip_sources(zip_path: Path, zf: zipfile.ZipFile, targets: list[str]) -> None:
    """
    targets: zip 내부 경로(ZipInfo.filename) 목록
    zip 파일의 마지막에 소스 내용을 추가 출력한다.
    """
    if not targets:
        return

    for name in targets:
        print("\n" + ("-" * 80))
        print(f"[FILE] {name}")

        try:
            with zf.open(name, "r") as fp:
                data = fp.read()
        except KeyError:
            print("[MISS] not found in zip")
            continue
        except Exception as e:
            print(f"[ERROR] read failed: {e}")
            continue

        # 텍스트로 출력 (바이너리면 깨질 수 있으니 replace)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")

        print(text.rstrip("\n"))


def list_zip(zip_path: Path, print_line: int, print_src: bool, filelist_targets: list[str]) -> int:
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

        for dt, name, zi in items[:print_line]:
            print(f"({diff_hms(dt)}) {dt.strftime('%Y-%m-%d %H:%M:%S')} | {to_mb(zi.file_size):6.2f} MB | {name}")

        # 기존 출력 유지 + 마지막에 추가 출력
        if print_src:
            print_zip_sources(zip_path, zf, filelist_targets)
            print("\n" + ("-" * 80))

    return 0


def main() -> int:
    print(f"> {now_str()}\n")

    cfg = load_config()

    print_line = int(cfg.get("print_line", 20))
    if print_line < 1:
        print_line = 1

    print_src = bool(cfg.get("print_src", False))
    filelist_targets = read_filelist(str(cfg.get("filelist", ""))) if print_src else []

    # zip_files 전체 순회 출력
    rc = 0
    for z in cfg["zip_files"]:
        zip_path = Path(str(z))
        print("=" * 80)
        r = list_zip(zip_path, print_line, print_src, filelist_targets)
        if r != 0:
            rc = r

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
