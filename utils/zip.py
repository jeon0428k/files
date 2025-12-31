import zipfile
import shutil
import yaml
from pathlib import Path
from datetime import datetime
import os
from typing import Dict, List, Tuple, Optional

CONFIG_FILE = "./config/zip.config.yml"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def file_size_mb(p: Path) -> float:
    return round(p.stat().st_size / (1024 * 1024), 2)


def file_mtime_str(p: Path) -> str:
    if not p.exists():
        return "N/A"
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def zip_datetime_str(zi: zipfile.ZipInfo) -> str:
    dt = datetime(*zi.date_time)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def diff_hms(zip_dt_str: Optional[str], src_path: Path) -> str:
    """
    zip 파일 시간과 실제 파일 수정시간 차이를 HH:MM:SS 로 반환
    zip_dt_str 가 없으면 "—"
    """
    if not zip_dt_str or not src_path.exists():
        return "—"

    zip_ts = datetime.strptime(zip_dt_str, "%Y-%m-%d %H:%M:%S").timestamp()
    src_ts = src_path.stat().st_mtime
    diff = abs(int(zip_ts - src_ts))

    h = diff // 3600
    m = (diff % 3600) // 60
    s = diff % 60
    return f"{h:02}:{m:02}:{s:02}"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_filelist(filelist_path: str) -> list[str]:
    """
    filelist 원문 라인을 그대로 읽는다.
    - 빈 줄/주석 제거
    - Windows '\' 는 '/' 로 통일
      (절대경로 판단/실제 파일 접근은 Path로 처리하므로 동작 문제 없음)
    """
    p = Path(filelist_path)
    if not p.exists():
        raise FileNotFoundError(p)

    items: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.append(s.replace("\\", "/"))
    return items


def to_zip_rel_from_absolute(root_path: Path, abs_path: Path) -> str:
    """
    절대경로를 zip 내부 경로(zip_rel)로 변환.
    - abs_path가 root_path 하위면 root_path 기준 상대경로로 구조 유지
    - 아니면 basename(파일명)만 사용(절대경로가 zip 엔트리로 들어가는 것 방지)
    """
    rp = root_path.resolve()
    ap = abs_path.resolve()
    try:
        rel = ap.relative_to(rp)
        zip_rel = rel.as_posix().lstrip("/")
        return zip_rel if zip_rel else ap.name
    except Exception:
        return abs_path.name


# WorkItem = (zip_rel, src_path, filelist_raw, is_abs_input)
WorkItem = Tuple[str, Path, str, bool]


def build_work_items(root_path: Path, filelist_lines: list[str]) -> List[WorkItem]:
    """
    filelist 한 줄을 (zip_rel, src_path, filelist_raw, is_abs_input) 로 정규화 + zip_rel 기준 DISTINCT
    - 상대경로: zip_rel=그대로, src_path=root_path/zip_rel, is_abs_input=False
    - 절대경로: src_path=그대로, zip_rel은 규칙에 따라 변환, is_abs_input=True
    - DISTINCT: 같은 zip_rel 이 여러 번 나오면 "뒤에 나온 항목"이 최종 우선권
    """
    seen: Dict[str, WorkItem] = {}

    for raw in filelist_lines:
        p = Path(raw)
        is_abs = p.is_absolute()

        if is_abs:
            src_path = p
            zip_rel = to_zip_rel_from_absolute(root_path, src_path)
        else:
            zip_rel = raw.replace("\\", "/").lstrip("/")
            src_path = (root_path / zip_rel)

        zip_rel = zip_rel.replace("\\", "/")

        # DISTINCT (뒤에 나온 항목 우선)
        seen[zip_rel] = (zip_rel, src_path, raw, is_abs)

    return list(seen.values())


def backup_zip_if_enabled(zip_file: Path, is_backup: bool) -> Optional[Path]:
    if not is_backup:
        return None

    backup_dir = zip_file.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = now_ts()
    backup_name = f"{zip_file.stem}_{ts}{zip_file.suffix}"
    backup_path = backup_dir / backup_name

    shutil.copy2(zip_file, backup_path)
    print(f"[BACKUP] {backup_path}")
    return backup_path


def precheck_sources(items: List[WorkItem]) -> Tuple[List[WorkItem], List[WorkItem]]:
    ok: List[WorkItem] = []
    miss: List[WorkItem] = []

    for zip_rel, src, raw, is_abs in items:
        if src.exists() and src.is_file():
            ok.append((zip_rel, src, raw, is_abs))
        else:
            miss.append((zip_rel, src, raw, is_abs))
    return ok, miss


def file_mtime_to_zip_datetime(p: Path) -> tuple:
    ts = p.stat().st_mtime
    dt = datetime.fromtimestamp(ts)
    sec = dt.second - (dt.second % 2)  # ZIP DOS time 2초 단위 보정
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, sec)


def clone_zipinfo(src_info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(filename=src_info.filename, date_time=src_info.date_time)
    zi.compress_type = src_info.compress_type
    zi.comment = src_info.comment
    zi.extra = src_info.extra
    zi.create_system = src_info.create_system
    zi.create_version = src_info.create_version
    zi.extract_version = src_info.extract_version
    zi.flag_bits = src_info.flag_bits
    zi.volume = getattr(src_info, "volume", 0)
    zi.internal_attr = src_info.internal_attr
    zi.external_attr = src_info.external_attr
    return zi


def rebuild_zip_preserve_others(zip_file: Path, patch_map: Dict[str, Path], allow_add: bool = True) -> Tuple[int, int, int]:
    """
    - patch_map(zip_rel -> src_path)에 있는 엔트리는 교체
    - 나머지는 ZipInfo/데이터 그대로 복사(수정시간 유지)
    - allow_add=True 이면 zip에 없던 항목은 추가
    """
    tmp_zip = zip_file.with_name(f"{zip_file.name}.tmp_{now_ts()}")

    patched = 0
    kept = 0

    with zipfile.ZipFile(zip_file, "r") as zsrc, zipfile.ZipFile(tmp_zip, "w") as zdst:
        src_names = set()

        for info in zsrc.infolist():
            src_names.add(info.filename)

            if info.filename in patch_map:
                new_path = patch_map[info.filename]
                new_info = clone_zipinfo(info)
                new_info.date_time = file_mtime_to_zip_datetime(new_path)

                with zdst.open(new_info, "w") as w, open(new_path, "rb") as r:
                    shutil.copyfileobj(r, w)

                patched += 1
            else:
                keep_info = clone_zipinfo(info)
                with zsrc.open(info, "r") as r, zdst.open(keep_info, "w") as w:
                    shutil.copyfileobj(r, w)
                kept += 1

        added = 0
        if allow_add:
            for zip_rel, src_path in patch_map.items():
                if zip_rel in src_names:
                    continue

                zi = zipfile.ZipInfo(filename=zip_rel, date_time=file_mtime_to_zip_datetime(src_path))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = (0o644 & 0xFFFF) << 16

                with zdst.open(zi, "w") as w, open(src_path, "rb") as r:
                    shutil.copyfileobj(r, w)

                added += 1

    os.replace(tmp_zip, zip_file)
    return patched, kept, added


def print_lists_in_format(
    zip_entries: set,
    zip_info_map: Dict[str, zipfile.ZipInfo],
    ok_sorted: List[WorkItem],
    miss_sorted: List[WorkItem],
    root_path: Path,
):
    # 출력 전에 root_path 출력
    print(f"[ROOT] {root_path}\n")

    added_list: List[WorkItem] = []
    patch_list: List[WorkItem] = []

    for zip_rel, src, raw, is_abs in ok_sorted:
        (patch_list if zip_rel in zip_entries else added_list).append((zip_rel, src, raw, is_abs))

    # 시간 내림차순 정렬(소스 파일 mtime 기준)
    added_list.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    patch_list.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    miss_sorted = sorted(
        miss_sorted,
        key=lambda x: x[1].stat().st_mtime if x[1].exists() else 0,
        reverse=True,
    )

    def filelist_hint(raw: str, is_abs: bool) -> str:
        # filelist에 절대경로가 있었다면 "(<filelist 경로>)" 추가
        return f" ({raw})" if is_abs else ""

    for zip_rel, src, raw, is_abs in added_list:
        zi = zip_info_map.get(zip_rel)
        zip_dt = zip_datetime_str(zi) if zi else None
        diff_str = diff_hms(zip_dt, src)
        zip_disp = zip_dt if zip_dt else "—"
        print(
            f"[ADDED] ({diff_str}) ({zip_disp}) {file_mtime_str(src)} | {file_size_mb(src):6.2f} MB | {zip_rel}"
            f"{filelist_hint(raw, is_abs)}"
        )

    for zip_rel, src, raw, is_abs in patch_list:
        zi = zip_info_map.get(zip_rel)
        zip_dt = zip_datetime_str(zi) if zi else None
        diff_str = diff_hms(zip_dt, src)
        zip_disp = zip_dt if zip_dt else "—"
        print(
            f"[PATCH] ({diff_str}) ({zip_disp}) {file_mtime_str(src)} | {file_size_mb(src):6.2f} MB | {zip_rel}"
            f"{filelist_hint(raw, is_abs)}"
        )

    for zip_rel, src, raw, is_abs in miss_sorted:
        print(
            f"[MISS]  {file_mtime_str(src):>19} | {0.00:6.2f} MB | {zip_rel}"
            f"{filelist_hint(raw, is_abs)}"
        )


def patch_zip(zip_file: str, root_path: str, filelist_lines: list[str], is_backup: bool):
    zip_file = Path(zip_file)
    root_path = Path(root_path)

    if not zip_file.exists():
        raise FileNotFoundError(zip_file)
    if not root_path.exists():
        raise FileNotFoundError(root_path)

    # filelist 정규화: (zip_rel, src_path, raw, is_abs) + DISTINCT
    items = build_work_items(root_path, filelist_lines)

    with zipfile.ZipFile(zip_file, "r") as z:
        zip_entries = set(z.namelist())
        zip_total_entries = len(zip_entries)
        zip_info_map = {zi.filename: zi for zi in z.infolist()}

    ok, miss = precheck_sources(items)

    ok_sorted = sorted(ok, key=lambda x: x[0])      # zip_rel 기준 정렬
    miss_sorted = sorted(miss, key=lambda x: x[0])  # zip_rel 기준 정렬

    patched_count = sum(1 for zip_rel, _, _, _ in ok_sorted if zip_rel in zip_entries)
    added_count = sum(1 for zip_rel, _, _, _ in ok_sorted if zip_rel not in zip_entries)
    miss_count = len(miss_sorted)

    if miss_sorted:
        print_lists_in_format(zip_entries, zip_info_map, ok_sorted, miss_sorted, root_path)
        print(f"\n✖ ABORT: added({added_count}), patched({patched_count}), kept({zip_total_entries}), miss({miss_count})")
        return

    # 1) backup + 목록 출력
    backup_zip_if_enabled(zip_file, is_backup)
    print_lists_in_format(zip_entries, zip_info_map, ok_sorted, [], root_path)

    # 2) 진행 여부 확인
    print("\nProceed? (y = YES / anything else = NO): ", end="")
    resp = input().strip()
    if resp.lower() != "y":
        print("\n✖ CANCELED")
        return

    patch_map = {zip_rel: src_path for zip_rel, src_path, _, _ in ok_sorted}
    patched, kept, added = rebuild_zip_preserve_others(zip_file, patch_map, allow_add=True)

    print(f"\n✔ DONE: added({added}), patched({patched}), kept({kept}), miss({miss_count})")


def main():
    print(f"> {now_str()}\n")

    cfg = load_config()
    filelist_lines = read_filelist(cfg["filelist"])

    patch_zip(
        cfg["zip_file"],
        cfg["root_path"],
        filelist_lines,
        bool(cfg.get("is_backup", False)),
    )


if __name__ == "__main__":
    main()
