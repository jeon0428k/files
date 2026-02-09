from pathlib import Path


def get_root() -> Path:
    """
    ROOT 반환
    """
    return Path(__file__).resolve().parents[1]


def resolve_path(*paths: str) -> Path:
    """
    ROOT 기준 절대경로 생성
    """
    return get_root().joinpath(*paths)
