from dataclasses import dataclass
from typing import Dict, List, Sequence, Any, Optional


@dataclass(frozen=True)
class ParsedArgs:
    values: List[str]      # 단순 값들 (순서 유지)
    kv: Dict[str, str]     # key=value (중복 시 마지막 값)


def parse_args(args: Sequence[str]) -> ParsedArgs:
    values: List[str] = []
    kv: Dict[str, str] = {}

    for arg in args:
        s = arg.strip()

        if "=" in s:
            key, value = s.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"Invalid key=value argument: {arg}")
            kv[key] = value
        else:
            values.append(s)

    return ParsedArgs(values=values, kv=kv)


# -----------------------------
# values 관련 헬퍼
# -----------------------------
def has_value(
    values: List[str],
    target: str,
    *,
    ignore_case: bool = True,
    default: Optional[bool] = None,
) -> Optional[bool]:
    """
    values 안에 target 이 존재하는지 여부
    - 존재하면 True
    - 없고 default 지정 → default
    - 없고 default 미지정 → None
    """
    if not values:
        return default

    if ignore_case:
        target = target.lower()
        found = any(v.lower() == target for v in values)
    else:
        found = target in values

    return True if found else default


def get_last_value(
    values: List[str],
    default: Any = None,
) -> Any:
    """
    단순 값 중 마지막 값
    - 없으면 default 반환
    - default 미지정 시 None
    """
    return values[-1] if values else default
