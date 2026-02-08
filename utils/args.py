from dataclasses import dataclass
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class ParsedArgs:
    bools: List[bool]        # true/false 들 (순서 유지)
    kv: Dict[str, str]       # key=value (중복 시 마지막 값)


def parse_args(args: Sequence[str]) -> ParsedArgs:
    bools: List[bool] = []
    kv: Dict[str, str] = {}

    for arg in args:
        s = arg.strip()
        sl = s.lower()

        if sl == "true":
            bools.append(True)
            continue

        if sl == "false":
            bools.append(False)
            continue

        if "=" in s:
            key, value = s.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValueError(f"Invalid key=value token: {arg}")
            kv[key] = value
            continue

        raise ValueError(f"Invalid argument: {arg}")

    return ParsedArgs(bools=bools, kv=kv)


def last_bool(bools: List[bool], default: bool = True) -> bool:
    """true/false 여러 개면 마지막 값 사용, 없으면 default"""
    return bools[-1] if bools else default
