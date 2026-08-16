from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ..firefox.firefoxGenerator import _parse_rom_launcher

from ...controller import generate_sdl_game_controller_config
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


class ChromeGenerator(Generator):
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        chrome_bin = _find_chrome_binary()
        url = "about:blank"
        user_agent = None
        if rom.name != "Chrome.chrome":
            with rom.open() as f:
                lines = f.read().splitlines()
            url, user_agent = _parse_rom_launcher(lines)

        force_x11 = system.config.get_bool("force_x11", False)

        commandArray = [
            chrome_bin,
            "--kiosk",
            "--force-device-scale-factor=1.5",
            "--no-default-browser-check",
        ]
        if user_agent:
            commandArray.append(f"--user-agent={user_agent}")
        commandArray.append(url)

        env = {}
        if playersControllers:
            env["SDL_GAMECONTROLLERCONFIG"] = generate_sdl_game_controller_config(playersControllers)

        return Command.Command(array=commandArray, env=env)

    def getMouseMode(self, config, rom):
        return False

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "chrome",
            "keys": {"exit": ["KEY_LEFTALT", "KEY_F4"]},
        }