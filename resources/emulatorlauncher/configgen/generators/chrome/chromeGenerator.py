from __future__ import annotations
import glob
import os
from pathlib import Path
import stat
import tempfile
from typing import TYPE_CHECKING

from configgen.controller import generate_sdl_game_controller_config
from ... import Command
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext


def _find_chrome_binary() -> str:
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "google-chrome",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "google-chrome"

def _make_wrapper(chrome_bin: str, url: str, playersControllers, user_agent: str | None = None) -> str:
    uid = os.getuid()
    wayland = os.environ.get("WAYLAND_DISPLAY", "wayland-0")
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    display = os.environ.get("DISPLAY", ":0")
    dbus = os.environ.get("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    home = os.environ.get("HOME", f"/home/{os.environ.get('USER', 'manuel')}")
    sdlconfig = generate_sdl_game_controller_config(playersControllers)
    sdl_export = f'export SDL_GAMECONTROLLERCONFIG="{sdlconfig}"' if playersControllers else ""
    ua_flag = f'    --user-agent="{user_agent}" \\' if user_agent else ""
    
    script = f"""#!/usr/bin/env bash
set -uo pipefail
trap 'rm -f "$0"' EXIT

{sdl_export}
export WAYLAND_DISPLAY="{wayland}"
export XDG_RUNTIME_DIR="{xdg_runtime}"
export DISPLAY="{display}"
export DBUS_SESSION_BUS_ADDRESS="{dbus}"
export HOME="{home}"
export GDK_BACKEND="x11"
export ELECTRON_OZONE_PLATFORM_HINT="x11"
export GDK_SCALE="1.5"
export QT_SCALE_FACTOR="1.5"

"{chrome_bin}" \\
    --kiosk \\
    --force-device-scale-factor=1.5 \\
    --no-sandbox \\
    --disable-dev-shm-usage \\
    --disable-gpu-shader-disk-cache \\
    --ozone-platform=x11 \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-session-crashed-bubble \\
    --disable-features=TranslateUI \\
    --no-first-run \\
    --no-default-browser-check \\{ua_flag}
    "{url}" > /dev/null 2>&1
    
echo "[chrome-wrapper] Chrome cerrado."
exit 0
"""
    fd, path = tempfile.mkstemp(prefix="chrome_wrapper_", suffix=".sh")
    os.write(fd, script.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path

class ChromeGenerator(Generator):
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        for old in glob.glob("/tmp/chrome_wrapper_*.sh"):
            try:
                os.remove(old)
            except OSError:
                pass
        
        chrome_bin = _find_chrome_binary()
        url = "about:blank"

        if rom.name != "Chrome.chrome":
            with rom.open() as f:
                lines = f.read().splitlines()
            if lines:
                url = lines[0].strip()
            user_agent = lines[1].strip() if len(lines) >= 2 and lines[1].strip() else None
        wrapper_path = _make_wrapper(chrome_bin, url, playersControllers, user_agent)
        return Command.Command(array=[wrapper_path], env={})

    def getMouseMode(self, config, rom):
        return False

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "chrome",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }