import os
from pathlib import Path

from platformdirs import user_data_dir


def default_data_dir() -> Path:
    """Stable product HOME (platformdirs). Ignores FORESHADOW_HOME and cwd."""
    return Path(user_data_dir("foreshadow"))


def resolve_data_dir() -> Path:
    home = os.environ.get("FORESHADOW_HOME")
    if home:
        return Path(home)
    return default_data_dir()


def resolve_log_dir(home: Path | None = None) -> Path:
    path = (home if home is not None else resolve_data_dir()) / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_unstable_path(path: Path | str) -> bool:
    """True for Desktop/Foreshadow checkouts and git worktrees (TCC/fragile)."""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        resolved = Path(path).expanduser()
    parts = resolved.parts
    if ".worktrees" in parts:
        return True
    for i, part in enumerate(parts):
        if part == "Desktop" and i + 1 < len(parts) and parts[i + 1] == "Foreshadow":
            return True
    return False
