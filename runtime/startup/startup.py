#!/usr/bin/env python3
"""
resources/startup/startup.py

Hook de arranque de RetroBox (equivalente al antiguo hook de bash
"frontend start"). Se ejecuta antes de lanzar EmulationStation:

  1. Carga variables de entorno desde .env (en la raíz del proyecto).
  2. Crea/rellena ~/.emulationstation (oneshot) y escribe emulationstation.ini.
  3. Limpia symlinks de juegos de PC obsoletos.
  4. Sincroniza launchers de Heroic/Lutris/Steam con EmulationStation.

Sustituye el hook homónimo de retrobox.sh; se puede invocar directamente:
    python3 resources/startup/startup.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from runtime.retrobox_paths import ENV_FILE, USERDATA

# --------------------------------------------------------------------------
# .env
# --------------------------------------------------------------------------

def load_env(env_path: Path) -> dict[str, str]:
    """Parsea un .env simple (KEY=VALUE), admite comentarios y comillas."""
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
        if key:
            env[key] = value
    return env


# --------------------------------------------------------------------------
# EmulationStation config
# --------------------------------------------------------------------------

def setup_emulationstation_config(rootdir: Path) -> None:
    """Crea el árbol .emulationstation (solo si no existe) y el .ini."""
    es_config_dir = rootdir / "frontend" / ".emulationstation"
    es_share_dir = rootdir / "frontend" / "share" / "emulationstation"

    if not es_config_dir.is_dir():
        es_config_dir.mkdir(parents=True, exist_ok=True)
        if es_share_dir.is_dir():
            shutil.copytree(es_share_dir, es_config_dir, dirs_exist_ok=True)

    retroarch_filters = (
        rootdir
        / "emulators/retroarch/RetroArch-Linux-x86_64.AppImage.home"
        / ".config/retroarch/filters"
    )

    ini_content = f"""# Ficheros
# Raíz y logs
root={rootdir}
log={rootdir}/logs
# ROMs y saves
saves={rootdir}/saves
screenshots={rootdir}/screenshots
# Temas
themes={rootdir}/frontend/themes
# Música
music={rootdir}/frontend/music
# Decoraciones/bezels
decorations={rootdir}/decorations
# Shaders
shaders={rootdir}/shaders/configs
# Videofilters
videofilters={retroarch_filters}/video
# Audiofilters
audiofilters={retroarch_filters}/audio
# RetroAchievement sounds
retroachievementsounds={rootdir}/frontend/retroachievements-sounds
# Padtokey (gamepadly)
system.padtokey={rootdir}/resources/utils/gamepadly/profiles
padtokey={rootdir}/resources/utils/gamepadly/user_profiles
# Zonas horarias
timezones=/usr/share/zoneinfo
"""
    (es_config_dir / "emulationstation.ini").write_text(ini_content, encoding="utf-8")


# --------------------------------------------------------------------------
# Sincronización de juegos de PC
# --------------------------------------------------------------------------

def clear_pcgame_symlinks(userdata: Path) -> None:
    """Elimina los enlaces .steam/.lynx/.heroic previos a resincronizar."""
    roms_dir = userdata / "roms"
    for system_name in ("steam", "heroic", "lutris"):
        system_dir = roms_dir / system_name
        if not system_dir.is_dir():
            continue
        for ext in ("steam", "lynx", "heroic"):
            for f in system_dir.glob(f"*.{ext}"):
                f.unlink(missing_ok=True)


def sync_pcgames(userdata: Path) -> None:
    """Lanza los sincronizadores heroic/lutris/steam, tolerando fallos (|| true)."""
    sync_dir = userdata / "resources" / "utils" / "pcgames-sync"
    for script_name in ("heroic-es-sync", "lutris-es-sync", "steam-es-sync"):
        script_path = sync_dir / script_name
        if not script_path.is_file():
            print(f"[startup] aviso: no encontrado {script_path}, se omite")
            continue
        try:
            subprocess.run([str(script_path)], check=False)
        except OSError as exc:
            print(f"[startup] aviso: fallo lanzando {script_name}: {exc}")

def main() -> None:
    

    env_vars = load_env(ENV_FILE)

    # Volcamos el .env al entorno real del proceso, para que también lo
    # hereden los subprocesos (sync scripts, etc.) vía os.environ.
    os.environ.update(env_vars)

    # El hook original usa ${USERDATA}, que retrobox.sh exporta antes de
    # llamar al hook y que no aparece en el .env mostrado. Si USERDATA no
    # está en el entorno, se asume igual a PROJECT_PATH; ajusta esta línea
    # si en tu caso USERDATA vive en otra ruta (p.ej. un subdirectorio).

    setup_emulationstation_config(USERDATA)
    clear_pcgame_symlinks(USERDATA)
    sync_pcgames(USERDATA)


if __name__ == "__main__":
    main()