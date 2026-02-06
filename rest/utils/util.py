# util.py
import ast
from typing import Any, Iterable, Optional, Union, Tuple, Dict


_MISSING = object()


def parse_dict_str(src: str) -> dict:
    """
    Python dict 리터럴 형태의 문자열을 dict로 변환한다.
    예) "{'a': 1, 'params': {'obj': 'abc'}}" -> dict

    주의:
    - JSON 문자열이 아니라 Python 표현식 문자열일 때 사용한다.
    - eval() 대신 ast.literal_eval 사용.
    """
    if not isinstance(src, str):
        raise ValueError("src must be a string")

    data = ast.literal_eval(src)
    if not isinstance(data, dict):
        raise ValueError("parsed object is not a dict")

    return data


def _iter_updates(
    updates: Union[str, Dict[str, Any], Iterable[Tuple[str, Any]]],
    value: Any = _MISSING,
) -> Iterable[Tuple[str, Any]]:
    """
    set_by_dot_path 입력을 표준 (path, value) iterator로 정규화.
    - (dot_path: str, value: Any) 단일 입력
    - dict {"a.b": 1, "c.d": 2}
    - iterable [("a.b", 1), ("c.d", 2)]
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
    dict 대상으로 dot path로 값 설정.
    여러 개 경로를 한 번에 지정 가능.

    사용 예)
      set_by_dot_path(d, "params.obj", "NEW")
      set_by_dot_path(d, {"a.b": 1, "c.d": 2}, create=True)
      set_by_dot_path(d, [("a.b", 1), ("c.d", 2)], create=False)

    create:
      - False: 경로 중 키가 없으면 KeyError
      - True : 경로 중 키가 없으면 dict 자동 생성
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
    if not dot_path or not isinstance(dot_path, str):
        raise ValueError("dot_path must be a non-empty string")

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
    - default를 전달하지 않으면: 경로 중 하나라도 없으면 KeyError
    - default를 전달하면: 없는 경로는 default 반환

    반환:
    - paths가 str이면 단일 값 반환
    - paths가 iterable이면 {path: value} dict 반환

    사용 예)
      v = get_by_dot_path(d, "params.obj")
      m = get_by_dot_path(d, ["a.b", "c.d"], default=None)
    """
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    if isinstance(paths, str):
        return _get_one_by_dot_path(data, paths, default=default)

    out: dict = {}
    for p in paths:
        out[p] = _get_one_by_dot_path(data, p, default=default)
    return out
