import os
from pathlib import Path
from typing import Iterable, List, Optional


_LOADED = False


def _env_file_candidates() -> Iterable[Path]:
    explicit_env_file = os.environ.get("TELEOP_ENV_FILE")
    if explicit_env_file:
        yield Path(explicit_env_file).expanduser()

    current = Path(__file__).resolve()
    for parent in (current.parent, *current.parents):
        yield parent / ".env"


def _strip_inline_comment(value: str) -> str:
    quote: Optional[str] = None
    for index, char in enumerate(value):
        if char in ("'", '"'):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _parse_env_value(raw_value: str) -> str:
    value = _strip_inline_comment(raw_value.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_env() -> None:
    global _LOADED
    if _LOADED:
        return

    for env_path in _env_file_candidates():
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue

            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = _parse_env_value(raw_value)
        break

    _LOADED = True


def env_str(name: str, default: str, aliases: Iterable[str] = ()) -> str:
    load_env()
    for key in (name, *aliases):
        value = os.environ.get(key)
        if value not in (None, ""):
            return value
    return default


def env_int(name: str, default: int, aliases: Iterable[str] = ()) -> int:
    value = env_str(name, str(default), aliases)
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float, aliases: Iterable[str] = ()) -> float:
    value = env_str(name, str(default), aliases)
    try:
        return float(value)
    except ValueError:
        return default


def env_bool(name: str, default: bool, aliases: Iterable[str] = ()) -> bool:
    value = env_str(name, str(default), aliases).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def env_list(name: str, default: List[str], aliases: Iterable[str] = ()) -> List[str]:
    value = env_str(name, ",".join(default), aliases)
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item] or default
