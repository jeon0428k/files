# util.py
import ast
from typing import Any, Optional


def set_by_dot_path(
    data: dict,
    dot_path: str,
    value: Any,
    *,
    create: bool = False,
) -> dict:
    """
    dict 대상으로 dot path("a.b.c")로 값 설정.

    - create=False: 경로 중 키가 없으면 KeyError
    - create=True : 경로 중 키가 없으면 dict 자동 생성

    예)
      d = {"params": {"obj": "abc"}}
      set_by_dot_path(d, "params.obj", "NEW") -> {"params": {"obj": "NEW"}}

      d = {}
      set_by_dot_path(d, "params.obj.sub", 1, create=True) -> {"params": {"obj": {"sub": 1}}}
    """
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    if not dot_path or not isinstance(dot_path, str):
        raise ValueError("dot_path must be a non-empty string")

    keys = dot_path.split(".")
    cur: Any = data

    for k in keys[:-1]:
        if not isinstance(cur, dict):
            raise KeyError(f"'{k}' parent is not a dict")

        if k not in cur:
            if create:
                cur[k] = {}
            else:
                raise KeyError(f"key not found: {k}")

        elif not isinstance(cur[k], dict):
            raise KeyError(f"'{k}' exists but is not a dict")

        cur = cur[k]

    last = keys[-1]
    if not isinstance(cur, dict):
        raise KeyError(f"cannot set '{last}', parent is not a dict")

    if not create and last not in cur:
        raise KeyError(f"key not found: {last}")

    cur[last] = value
    return data


def set_by_dot_path_str(
    src: str,
    dot_path: str,
    value: Any,
    *,
    create: bool = False,
) -> dict:
    """
    str로 된 Python dict 표현을 파싱한 뒤 dot path로 값 설정하고 dict 반환.

    - src 예:
      "{'col1': 'a', 'params': {'obj': 'abc'}}"

    주의:
      - eval() 대신 ast.literal_eval 사용 (상대적으로 안전)
      - 입력이 JSON 문자열이면 json.loads 사용해야 함
    """
    if not isinstance(src, str):
        raise ValueError("src must be a string")

    data = ast.literal_eval(src)
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    return set_by_dot_path(data, dot_path, value, create=create)


def get_by_dot_path(
    data: dict,
    dot_path: str,
    *,
    default: Any = _MISSING,
) -> Any:
    """
    dict에서 dot path로 값 조회.

    동작:
    - default가 전달되면(정의되면) 경로 없을 시 default 반환
    - default가 전달되지 않으면 경로 없을 시 KeyError

    예)
      get_by_dot_path(d, "a.b")                 -> 없으면 KeyError
      get_by_dot_path(d, "a.b", default=None)   -> 없으면 None 반환
      get_by_dot_path(d, "a.b", default=0)      -> 없으면 0 반환
    """
    if not isinstance(data, dict):
        raise ValueError("root is not a dict")

    if not dot_path or not isinstance(dot_path, str):
        raise ValueError("dot_path must be a non-empty string")

    keys = dot_path.split(".")
    cur: Any = data

    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            if default is _MISSING:
                raise KeyError(f"key not found: {k}")
            return default
        cur = cur[k]

    return cur
