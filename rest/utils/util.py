# util.py
import ast
import json
from typing import Any, Iterable, Union, Tuple, Dict


_MISSING = object()


def parse_dict(src: Union[str, dict]) -> dict:
    """
    str 또는 dict 입력을 dict로 변환한다.

    처리 순서:
    1) 이미 dict면 그대로 반환
    2) json.loads 시도 (JSON 표준)
    3) ast.literal_eval 시도 (Python dict 리터럴)

    실패 시 ValueError 발생
    """
    if isinstance(src, dict):
        return src

    if not isinstance(src, str):
        raise ValueError("src must be str or dict")

    s = src.strip()
    if not s:
        raise ValueError("empty string")

    # 1. JSON 우선
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Python literal fallback
    try:
        data = ast.literal_eval(s)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    raise ValueError("failed to parse string to dict (not JSON nor Python literal)")


def _iter_updates(
    updates: Union[str, Dict[str, Any], Iterable[Tuple[str, Any]]],
    value: Any = _MISSING,
) -> Iterable[Tuple[str, Any]]:
    """
    set_by_dot_path 입력을 (dot_path, value) iterable로 정규화.
    """
    if isinstance(updates, str):
        if value is _MISSING:
            raise ValueError("value is required when updates is a dot_path string")
        return [(updates, value)]

    if isinstance(updates, dict):
        return list(updates.items())

    return list(updates)


def set_by_dot_path(
    data: dict,
    updates: Union[str, Dict[str, Any], Iterable[Tuple[str, Any]]],
    value: Any = _MISSING,
    *,
    create: bool = False,
) -> dict:
    """
    dict 대상으로 dot path("a.b.c")로 값 설정.
    여러 개 경로를 한 번에 지정 가능.

    create:
      - False: 키 없으면 KeyError
      - True : 키 없으면 dict 자동 생성
    """
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    pairs = _iter_updates(updates, value)

    for dot_path, v in pairs:
        if not dot_path or not isinstance(dot_path, str):
            raise ValueError("dot_path must be a non-empty string")

        keys = dot_path.split(".")
        cur: Any = data

        for k in keys[:-1]:
            if not isinstance(cur, dict):
                raise KeyError(f"'{k}' parent is not a dict (path='{dot_path}')")

            if k not in cur:
                if create:
                    cur[k] = {}
                else:
                    raise KeyError(f"key not found: {k} (path='{dot_path}')")

            elif not isinstance(cur[k], dict):
                raise KeyError(f"'{k}' exists but is not a dict (path='{dot_path}')")

            cur = cur[k]

        last = keys[-1]
        if not isinstance(cur, dict):
            raise KeyError(f"cannot set '{last}', parent is not a dict (path='{dot_path}')")

        if not create and last not in cur:
            raise KeyError(f"key not found: {last} (path='{dot_path}')")

        cur[last] = v

    return data


def _get_one_by_dot_path(
    data: dict,
    dot_path: str,
    *,
    default: Any = _MISSING,
) -> Any:
    keys = dot_path.split(".")
    cur: Any = data

    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            if default is _MISSING:
                raise KeyError(f"key not found: {k} (path='{dot_path}')")
            return default
        cur = cur[k]

    return cur


def get_by_dot_path(
    data: dict,
    paths: Union[str, Iterable[str]],
    *,
    default: Any = _MISSING,
) -> Any:
    """
    dict에서 dot path로 값 조회.
    여러 개 경로를 한 번에 지정 가능.

    규칙:
    - default 미지정: 경로 없으면 KeyError
    - default 지정: 경로 없으면 default 반환

    반환:
    - paths가 str → 단일 값
    - paths가 iterable → {path: value} dict
    """
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    if isinstance(paths, str):
        return _get_one_by_dot_path(data, paths, default=default)

    out: dict = {}
    for p in paths:
        out[p] = _get_one_by_dot_path(data, p, default=default)
    return out
