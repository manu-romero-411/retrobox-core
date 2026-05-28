from __future__ import annotations
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
LAUNCH_TIMEOUT = 90  # segundos esperando a que aparezca el reaper


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


def _make_wrapper(steam_bin: str, app_id: str | None) -> str:
    MAX_TOTAL = 7200  # 2h timeout global de seguridad

    if app_id:
        launch_cmd = f'"{steam_bin}" -silent -applaunch {app_id} > /dev/null 2>&1 &'
        monitor = f"""\
APPID="{app_id}"
LAUNCH_TIMEOUT={LAUNCH_TIMEOUT}
POLL={POLL_INTERVAL}
MAX_TOTAL={MAX_TOTAL}

START=$(date +%s)
_elapsed() {{ echo $(( $(date +%s) - START )); }}
_timeout() {{ [ "$(_elapsed)" -ge "$MAX_TOTAL" ]; }}

# Fase 1: esperar a que aparezca el reaper (puede tardar si compila shaders)
echo "[steam-wrapper] Esperando arranque del juego (AppId=$APPID)..."
APPEARED=0
DEADLINE=$(( START + LAUNCH_TIMEOUT ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    if pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
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

# Fase 2: esperar a que desaparezca, con confirmación anti-relaunch
while true; do
    _timeout && echo "[steam-wrapper] Timeout global, saliendo." && exit 0

    if ! pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
        # Reaper desapareció — esperar y confirmar que no vuelve
        # (Steam puede relanzar el proceso tras compilar shaders)
        echo "[steam-wrapper] Reaper desapareció, confirmando..."
        sleep 8
        if ! pgrep -f "SteamLaunch AppId=$APPID" > /dev/null 2>&1; then
            echo "[steam-wrapper] Juego AppId=$APPID terminado."
            exit 0
        fi
        echo "[steam-wrapper] Falsa alarma, el juego relanzó (shaders?), continuando..."
    fi

    sleep "$POLL"
done
"""
    else:
        launch_cmd = f'"{steam_bin}" -silent > /dev/null 2>&1 &'
        monitor = f"""\
echo "[steam-wrapper] Sin appid, esperando a que Steam cierre..."
sleep 5
while pgrep -x steam > /dev/null 2>&1; do
    sleep {POLL_INTERVAL}
done
echo "[steam-wrapper] Steam cerrado."
"""

    script = f"""#!/usr/bin/env bash
set -uo pipefail
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
        steam_bin = _find_steam_binary()
        app_id: str | None = None

        if rom.name != "Steam.steam":
            with rom.open() as f:
                first_line = f.readline().strip()
            # first_line: "steam://rungameid/24780"
            if first_line.startswith("steam://rungameid/"):
                app_id = first_line.removeprefix("steam://rungameid/")

        wrapper_path = _make_wrapper(steam_bin, app_id)

        env = {"SDL_JOYSTICK_HIDAPI_XBOX": "0"}

        # runCommand hará Popen([wrapper_path]) + communicate() → bloqueante
        return Command.Command(array=[wrapper_path], env=env)

    def getMouseMode(self, config, rom):
        return True

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "steam",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }