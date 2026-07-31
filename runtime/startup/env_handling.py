import os
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.is_file():
        return env
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Un valor vacío ("VAR=" o "VAR=\"\"") se interpreta como "sin definir":
        # cae al default de retrobox_paths.py en vez de sobreescribirlo con "".
        if key and value:
            env[key] = value
    return env

def apply_env_defaults(rootdir) -> None:
    for key, value in load_env(Path(f"{rootdir}/.env")).items():
        os.environ.setdefault(key, value)