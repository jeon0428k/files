from pathlib import Path


def get_workspace_root() -> Path:
    """
    워크스페이스 루트 반환
    기준:
      D:/program/deploy/run_all.py
      D:/program/work.py
      D:/program/check.py
    → 모두 D:/program 을 루트로 간주
    """
    return Path(__file__).resolve().parents[1]


def resolve_path(*paths: str) -> Path:
    """
    워크스페이스 기준 절대경로 생성
    """
    return get_workspace_root().joinpath(*paths)
