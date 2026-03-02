import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    # 1) 배치에서 강제로 지정하고 싶으면 APP_ROOT 사용 가능
    env_root = os.getenv("APP_ROOT")
    if env_root:
        return Path(env_root).resolve()

    # 2) python <script.py> 로 실행 시 argv[0] = script 경로
    argv0 = sys.argv[0]
    if argv0:
        p = Path(argv0)
        if p.exists():
            return p.resolve().parent

    # 3) fallback: 현재 작업 디렉토리
    return Path.cwd().resolve()


def resolve_path(*paths: str) -> Path:
    return get_app_root().joinpath(*paths)
