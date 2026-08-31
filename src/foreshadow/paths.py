import os
from pathlib import Path

from platformdirs import user_data_dir


def resolve_data_dir() -> Path:
    home = os.environ.get("FORESHADOW_HOME")
    if home:
        return Path(home)
    return Path(user_data_dir("foreshadow"))
