import yaml
import zipfile
import subprocess
import tempfile
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

    # class 디컴파일 옵션
    cfg["decompile_class"] = bool(cfg.get("decompile_class", False))
    cfg["cfr_jar"] = cfg.get("cfr_jar", "")
    cfg["use_javap_fallback"] = bool(cfg.get("use_javap_fallback", True))

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


def run_cmd(cmd: list[str], timeout_sec: int = 60) -> tuple[int, str]:
    """
    외부 커맨드 실행 유틸.
    stdout+stderr 합쳐서 반환.
    """
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, f"[ERROR] command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "[ERROR] command timeout"
    except Exception as e:
        return 1, f"[ERROR] command failed: {e}"


def decompile_class_bytes(class_bytes: bytes, cfg: dict) -> str:
    """
    .class 바이트를 임시 파일로 저장 후 디컴파일 결과 문자열을 반환.
    - CFR jar가 있으면 outputdir로 .java 생성 후 읽어서 출력
    - 없으면 javap -c로 바이트코드 디스어셈블
    """
    cfr_jar = str(cfg.get("cfr_jar", "")).strip()
    use_javap = bool(cfg.get("use_javap_fallback", True))

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        class_file = tmp_dir / "Target.class"
        class_file.write_bytes(class_bytes)

        # 1) CFR 우선 (stdout 옵션 없는 버전 대응: outputdir로 생성된 .java 읽기)
        if cfr_jar:
            jar_path = Path(cfr_jar)
            if jar_path.exists():
                out_dir = tmp_dir / "cfr_out"
                out_dir.mkdir(parents=True, exist_ok=True)

                cmd = [
                    "java",
                    "-jar",
                    str(jar_path),
                    str(class_file),
                    "--outputdir",
                    str(out_dir),
                ]
                rc, out = run_cmd(cmd)

                # CFR이 .java 파일을 생성했으면 그걸 읽어서 반환
                java_files = sorted(out_dir.rglob("*.java"))
                if java_files:
                    try:
                        return java_files[0].read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        return f"[ERROR] CFR output read failed: {e}"

                # 생성 파일이 없으면 CFR 출력(에러 포함) 보여주기
                return f"[ERROR] CFR failed (rc={rc})\n{out}".rstrip()

        # 2) javap fallback (소스가 아니라 바이트코드)
        if use_javap:
            rc, out = run_cmd(["javap", "-c", "-p", str(class_file)])
            if rc == 0 and out.strip():
                return out
            return f"[ERROR] javap failed (rc={rc})\n{out}".rstrip()

        return "[ERROR] decompiler not configured (set cfr_jar or enable javap fallback)"


def print_zip_sources(zip_path: Path, zf: zipfile.ZipFile, targets: list[str], cfg: dict) -> None:
    """
    targets: zip 내부 경로(ZipInfo.filename) 목록
    zip 파일의 마지막에 소스 내용을 추가 출력한다.
    """
    if not targets:
        return

    decompile_class = bool(cfg.get("decompile_class", False))

    for name in targets:
        print("\n" + ("-" * 80))
        print(f"[FILE] {name}")

        try:
            with zf.open(name, "r") as fp:
                data = fp.read()
        except KeyError:
            print("[MISS] not found")
            continue
        except Exception as e:
            print(f"[ERROR] read failed: {e}")
            continue

        # .class이면 디컴파일 출력
        if decompile_class and name.lower().endswith(".class"):
            print("[DECOMPILE]\n")
            print(decompile_class_bytes(data, cfg))
            continue

        # 일반 텍스트 파일 출력
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")

        print(text.rstrip("\n"))


def list_zip(zip_path: Path, print_line: int, print_src: bool, filelist_targets: list[str], cfg: dict) -> int:
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
            print_zip_sources(zip_path, zf, filelist_targets, cfg)
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
        r = list_zip(zip_path, print_line, print_src, filelist_targets, cfg)
        if r != 0:
            rc = r

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
