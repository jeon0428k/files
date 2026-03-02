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
    zip 파일 시간과 실제 파일 수정시간 차이를 {일수}d HH:MM:SS 로 반환
    - 일수는 3자리 고정 (예: 001d 02:10:05)
    - zip_dt_str 가 없으면 "—"
    """
    if not zip_dt_str or not src_path.exists():
        return "—"

    zip_ts = datetime.strptime(zip_dt_str, "%Y-%m-%d %H:%M:%S").timestamp()
    src_ts = src_path.stat().st_mtime
    diff = abs(int(zip_ts - src_ts))

    days = diff // 86400
    diff = diff % 86400

    h = diff // 3600
    m = (diff % 3600) // 60
    s = diff % 60

    return f"{days:03d}d {h:02}:{m:02}:{s:02}"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_filelist(filelist_path: str) -> list[str]:
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
    rp = root_path.resolve()
    ap = abs_path.resolve()
    try:
        rel = ap.relative_to(rp)
        zip_rel = rel.as_posix().lstrip("/")
        return zip_rel if zip_rel else ap.name
    except Exception:
        return abs_path.name


WorkItem = Tuple[str, Path, str, bool]


def build_work_items(root_path: Path, filelist_lines: list[str]) -> List[WorkItem]:
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
        seen[zip_rel] = (zip_rel, src_path, raw, is_abs)

    return list(seen.values())


def ensure_out_dir(out_path: str) -> Path:
    p = Path(out_path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def backup_existing_out_if_enabled(final_out: Path, is_backup: bool, out_dir: Path) -> Optional[Path]:
    if not is_backup or not final_out.exists():
        return None

    backup_dir = out_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = now_ts()
    backup_name = f"{final_out.stem}_{ts}{final_out.suffix}"
    backup_path = backup_dir / backup_name

    shutil.copy2(final_out, backup_path)
    print(f"[BACKUP] {backup_path.resolve()}")
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
    sec = dt.second - (dt.second % 2)
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


def build_output_paths(src_zip: Path, out_dir: Path) -> Tuple[Path, Path]:
    final_out = out_dir / src_zip.name
    tmp_out = out_dir / f"{src_zip.stem}_{now_ts()}{src_zip.suffix}"
    return final_out, tmp_out


def rebuild_zip_to_new(
    src_zip: Path,
    out_zip: Path,
    patch_map: Dict[str, Path],
    allow_add: bool = True,
) -> Tuple[int, int, int]:

    tmp_zip = out_zip.with_name(f"{out_zip.name}.tmp_{now_ts()}")

    patched = 0
    kept = 0

    with zipfile.ZipFile(src_zip, "r") as zsrc, zipfile.ZipFile(tmp_zip, "w") as zdst:
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

    if out_zip.exists():
        out_zip.unlink()
    os.replace(tmp_zip, out_zip)

    return patched, kept, added


def print_lists_in_format(
    zip_entries: set,
    zip_info_map: Dict[str, zipfile.ZipInfo],
    ok_sorted: List[WorkItem],
    miss_sorted: List[WorkItem],
    root_path: Path,
):
    print(f"[ROOT] {root_path}\n")

    added_list: List[WorkItem] = []
    patch_list: List[WorkItem] = []

    for zip_rel, src, raw, is_abs in ok_sorted:
        (patch_list if zip_rel in zip_entries else added_list).append((zip_rel, src, raw, is_abs))

    added_list.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    patch_list.sort(key=lambda x: x[1].stat().st_mtime, reverse=True)
    miss_sorted = sorted(
        miss_sorted,
        key=lambda x: x[1].stat().st_mtime if x[1].exists() else 0,
        reverse=True,
    )

    def filelist_hint(raw: str, is_abs: bool) -> str:
        return f" ({raw})" if is_abs else ""

    for zip_rel, src, raw, is_abs in added_list:
        zi = zip_info_map.get(zip_rel)
        zip_dt = zip_datetime_str(zi) if zi else None
        diff_str = diff_hms(zip_dt, src)
        zip_disp = zip_dt if zip_dt else "—"
        print(
            f"[ADDED] ({diff_str}) ({zip_disp}) {file_mtime_str(src)} | "
            f"{file_size_mb(src):6.2f} MB | {zip_rel}{filelist_hint(raw, is_abs)}"
        )

    for zip_rel, src, raw, is_abs in patch_list:
        zi = zip_info_map.get(zip_rel)
        zip_dt = zip_datetime_str(zi) if zi else None
        diff_str = diff_hms(zip_dt, src)
        zip_disp = zip_dt if zip_dt else "—"
        print(
            f"[PATCH] ({diff_str}) ({zip_disp}) {file_mtime_str(src)} | "
            f"{file_size_mb(src):6.2f} MB | {zip_rel}{filelist_hint(raw, is_abs)}"
        )

    for zip_rel, src, raw, is_abs in miss_sorted:
        print(
            f"[MISS]  {file_mtime_str(src):>19} | {0.00:6.2f} MB | "
            f"{zip_rel}{filelist_hint(raw, is_abs)}"
        )


def patch_zip(
    src_zip_file: str,
    root_path: str,
    filelist_lines: list[str],
    is_backup: bool,
    out_dir: Path,
    is_confirm: bool,   # ★ 추가
):
    src_zip = Path(src_zip_file)
    root_path = Path(root_path)

    items = build_work_items(root_path, filelist_lines)

    with zipfile.ZipFile(src_zip, "r") as z:
        zip_entries = set(z.namelist())
        zip_total_entries = len(zip_entries)
        zip_info_map = {zi.filename: zi for zi in z.infolist()}

    ok, miss = precheck_sources(items)

    ok_sorted = sorted(ok, key=lambda x: x[0])
    miss_sorted = sorted(miss, key=lambda x: x[0])

    patched_count = sum(1 for zip_rel, _, _, _ in ok_sorted if zip_rel in zip_entries)
    added_count = sum(1 for zip_rel, _, _, _ in ok_sorted if zip_rel not in zip_entries)
    miss_count = len(miss_sorted)

    if miss_sorted:
        print_lists_in_format(zip_entries, zip_info_map, ok_sorted, miss_sorted, root_path)
        print(
            f"\n✖ ABORT: added({added_count}), patched({patched_count}), "
            f"kept({zip_total_entries}), miss({miss_count})"
        )
        return

    print_lists_in_format(zip_entries, zip_info_map, ok_sorted, [], root_path)

    # ★★★ 핵심 변경 부분 ★★★
    if is_confirm:
        print("\nProceed? (y = YES / anything else = NO): ", end="")
        resp = input().strip()
        if resp.lower() != "y":
            print("\n✖ CANCELED")
            return
    else:
        print("\n[SKIP CONFIRM]")

    final_out, tmp_out = build_output_paths(src_zip, out_dir)

    backup_existing_out_if_enabled(final_out, is_backup, out_dir)

    patch_map = {zip_rel: src_path for zip_rel, src_path, _, _ in ok_sorted}

    patched, kept, added = rebuild_zip_to_new(src_zip, tmp_out, patch_map, allow_add=True)

    if final_out.exists():
        final_out.unlink()
    os.replace(tmp_out, final_out)

    print(f"\n[OUT] {final_out.resolve()}")
    print(
        f"\n✔ DONE: added({added}), patched({patched}), "
        f"kept({kept}), miss({miss_count})"
    )


def main():
    print(f"> {now_str()}\n")

    cfg = load_config()
    filelist_lines = read_filelist(cfg["filelist"])

    zip_files = cfg.get("zip_files", [])
    if isinstance(zip_files, str):
        zip_files = [zip_files]
    if not isinstance(zip_files, list):
        raise ValueError("config zip_files must be a list (or a string)")

    out_path = cfg.get("out_path", "./out")
    out_dir = ensure_out_dir(out_path)

    is_confirm = bool(cfg.get("is_confirm", True))   # ★ 추가 (기본값 true)

    zip_paths = [Path(z) for z in zip_files]
    missing = [p for p in zip_paths if not p.exists()]

    if missing:
        print("✖ ABORT: zip_files 중 존재하지 않는 zip 파일이 있습니다.\n")
        for p in missing:
            print(f"[MISSING] {p}")
        return

    for zf in zip_files:
        print(f"\n=== SOURCE ZIP: {zf} ===")
        patch_zip(
            zf,
            cfg["root_path"],
            filelist_lines,
            bool(cfg.get("is_backup", False)),
            out_dir,
            is_confirm,   # ★ 전달
        )


if __name__ == "__main__":
    main()
