from __future__ import annotations
import glob
import os
import sys
import subprocess
import time
import tempfile
import stat
from pathlib import Path
from typing import TYPE_CHECKING
from ... import Command
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext

POLL_INTERVAL = 4
LAUNCH_TIMEOUT = 300  # segundos esperando a que aparezca el reaper / Steam

BIGPICTURE_ROM_NAME = "steam.steam"
BIGPICTURE_ROM_CONTENT = "steam"


def _find_steam_binary() -> str:
    candidates = [
        "/usr/bin/steam",
        "/usr/local/bin/steam",
        str(Path.home() / ".local/bin/steam"),
        "steam",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "steam"


def _is_bigpicture_rom(rom) -> bool:
    """
    rom "steam.webapp" cuyo único contenido (tras strip) es la palabra "steam"
    -> lanzar Steam en modo Big Picture en vez de un applaunch de un juego concreto.
    """
    if rom.name.lower() != BIGPICTURE_ROM_NAME:
        return False
    try:
        with rom.open() as f:
            content = f.read().strip()
    except OSError:
        return False
    return content == BIGPICTURE_ROM_CONTENT


def _make_wrapper(steam_bin: str, app_id: str | None, big_picture: bool = False) -> str:
    MAX_TOTAL = 7200  # 2h timeout global de seguridad

    if big_picture:
        # Big Picture: no hay AppId que vigilar, ni tiene sentido pollear
        # RunningAppID/procesos de juego concretos. Solo esperamos a que
        # Steam arranque y luego a que el propio Steam se cierre.
        launch_cmd = f'"{steam_bin}" -bigpicture > /dev/null 2>&1 &'
        monitor = f"""\
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}

echo "[steam-wrapper] Esperando arranque de Steam (Big Picture)..."
START=$(date +%s)
_elapsed() {{ echo $(( $(date +%s) - START )); }}

DEADLINE=$(( START + LAUNCH_TIMEOUT ))
APPEARED=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if pgrep -x steam > /dev/null 2>&1; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[steam-wrapper] Steam no arrancó tras ${{LAUNCH_TIMEOUT}}s, saliendo."
    exit 0
fi

echo "[steam-wrapper] Steam detectado, esperando a que se cierre (sin vigilar juegos)..."

while true; do
    if [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; then
        echo "[steam-wrapper] Timeout global, saliendo."
        exit 0
    fi
    if ! pgrep -x steam > /dev/null 2>&1; then
        echo "[steam-wrapper] Steam se ha cerrado."
        exit 0
    fi
    sleep "$POLL"
done
"""
    else:
        launch_cmd = ""
        monitor = ""
        if app_id:
            launch_cmd = f'"{steam_bin}" -silent -applaunch {app_id} > /dev/null 2>&1 &'
            monitor = f"""\
APPID="{app_id}"
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}  # shaders pueden tardar varios minutos

REG="$HOME/.steam/registry.vdf"
[ -f "$REG" ] || REG="$HOME/.local/share/Steam/registry.vdf"

_running_appid() {{
    [ -f "$REG" ] || return 1
    awk -F'"' '/"RunningAppID"/ {{ print $4; exit }}' "$REG"
}}

START=$(date +%s)
_elapsed() {{ echo $(( $(date +%s) - START )); }}
_timeout() {{ [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; }}

echo "[steam-wrapper] Esperando arranque del juego (AppId=$APPID)..."
APPEARED=0
DEADLINE=$(( START + LAUNCH_TIMEOUT ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    RID="$(_running_appid)"
    if [ -n "$RID" ] && [ "$RID" = "$APPID" ]; then
        APPEARED=1
        break
    fi
    # fallback si no hay registry.vdf legible
    if [ -z "$RID" ] && pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
        APPEARED=1
        break
    fi
    sleep "$POLL"
done

if [ "$APPEARED" -eq 0 ]; then
    echo "[steam-wrapper] Juego no detectado tras ${{LAUNCH_TIMEOUT}}s, saliendo."
    exit 0
fi

echo "[steam-wrapper] Juego detectado, monitorizando cierre..."

while true; do
    _timeout && echo "[steam-wrapper] Timeout global, saliendo." && exit 0

    RID="$(_running_appid)"
    if [ -n "$RID" ]; then
        # registry.vdf disponible: fuente fiable, sin parpadeos por shaders
        if [ "$RID" != "$APPID" ]; then
            echo "[steam-wrapper] Juego AppId=$APPID terminado (RunningAppID=$RID)."
            exit 0
        fi
    else
        # fallback al método antiguo si no hay registry.vdf
        if ! pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
            sleep 8
            if ! pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
                echo "[steam-wrapper] Juego AppId=$APPID terminado."
                exit 0
            fi
        fi
    fi

    sleep "$POLL"
done
"""

    script = f"""#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT
echo "[steam-wrapper] Lanzando Steam..."
{launch_cmd}
{monitor}
exit 0
"""
    fd, path = tempfile.mkstemp(prefix="steam_wrapper_", suffix=".sh")
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path

class SteamGenerator(Generator):

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        for old in glob.glob("/tmp/steam_wrapper_*.sh"):
            try:
                os.remove(old)
            except OSError:
                pass

        steam_bin = _find_steam_binary()
        app_id: str | None = None
        big_picture = _is_bigpicture_rom(rom)

        if not big_picture:
            with rom.open() as f:
                first_line = f.readline().strip()
            # first_line: "steam://rungameid/24780"
            if first_line.startswith("steam://rungameid/"):
                app_id = first_line.removeprefix("steam://rungameid/")

        wrapper_path = _make_wrapper(steam_bin, app_id, big_picture=big_picture)

        #env = {"SDL_JOYSTICK_HIDAPI_XBOX": "0"}
        env = {}
        # runCommand hará Popen([wrapper_path]) + communicate() → bloqueante
        return Command.Command(array=[wrapper_path], env=env)

    def getMouseMode(self, config, rom):
        return True

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "steam",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }