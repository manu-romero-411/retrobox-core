from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING

from configgen.controller import generate_sdl_game_controller_config
from ... import Command
from ..Generator import Generator

if TYPE_CHECKING:
    from ...batoceraTypes import HotkeysContext


def _find_firefox_binary() -> str:
    candidates = [
        "/usr/bin/firefox",
        "/usr/bin/firefox-esr",
        "/usr/local/bin/firefox",
        "firefox",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "firefox"


class FirefoxGenerator(Generator):

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        firefox_bin = _find_firefox_binary()
        url = "about:blank"

        if rom.name != "Firefox.firefox":
            with rom.open() as f:
                lines = f.read().splitlines()

            url = lines[0].strip() if lines else "about:blank"
            user_agent = lines[1].strip() if len(lines) >= 2 else None
        command_array = [
            firefox_bin,
            "--kiosk",
            "--no-remote",
            *(["--override-user-agent", user_agent] if user_agent else []),
            url,
        ]
        env = {
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
            "GDK_SCALE": "1.5",
            "QT_SCALE_FACTOR": "1.5",
            "MOZ_ENABLE_WAYLAND": os.environ.get("MOZ_ENABLE_WAYLAND", "1"),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "wayland-0"),
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
            "DISPLAY": os.environ.get("DISPLAY", ":0"),
            "DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus"),
            "HOME": os.environ.get("HOME", str(Path.home())),
        }

        return Command.Command(array=command_array, env=env)

    def getMouseMode(self, config, rom):
        return False

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "firefox",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }