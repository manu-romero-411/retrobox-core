from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.launcher.configgen import Command
from runtime.launcher.configgen.Emulator import generate_bash_wrapper
from runtime.launcher.configgen.exceptions import MissingCore
from runtime.launcher.configgen.generators.Generator import Generator

from runtime.launcher.configgen.generators.libretro.libretroPaths import (
    _RETROARCH_BIN,
    _RETROARCH_CFGDIR,
    _RETROARCH_XDG,
    RETROARCH_CORES,
    RETROARCH_CFG,
    RETROARCH_SHADERS,
    RETROARCH_SHARE
)
from runtime.paths import (
    OVERLAYS,
    _SHADERS_DIR,
    configure_emulator,
    mkdir_if_not_exists
)
from runtime.launcher.configgen.settings.unixSettings import UnixSettings
from runtime.launcher.configgen.utils import vulkan
from runtime.launcher.configgen.generators.libretro import libretroConfig, libretroControllers
from runtime.launcher.configgen.utils import videoMode

if TYPE_CHECKING:
    from runtime.launcher.configgen.Emulator import Emulator
    from runtime.launcher.configgen.batoceraTypes import HotkeysContext

_logger = logging.getLogger(__name__)


class LibretroGenerator(Generator):

    def supportsInternalBezels(self):
        return True

    def usesOpenGLDirectPreload(self, config) -> bool:
        return config.get("gfxbackend") == "glcore" or config.get("gfxbackend") == "gl"

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "retroarch",
            "keys": {
                "exit": ["KEY_LEFTSHIFT", "KEY_ESC"],
                "menu": ["KEY_LEFTSHIFT", "KEY_F1"],
                "pause": ["KEY_LEFTSHIFT", "KEY_P"],
                "coin": "KEY_F12",
                "save_state": ["KEY_LEFTSHIFT", "KEY_F3"],
                "restore_state": ["KEY_LEFTSHIFT", "KEY_F4"],
                "previous_slot": ["KEY_LEFTSHIFT", "KEY_F6"],
                "next_slot": ["KEY_LEFTSHIFT", "KEY_F5"],
                "rewind": ["KEY_LEFTSHIFT", "KEY_F11"],
                "fastforward": ["KEY_LEFTSHIFT", "KEY_F12"],
                "reset": ["KEY_LEFTSHIFT", "KEY_F10"],
                "translation": ["KEY_LEFTSHIFT", "KEY_F9"],
            }
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        self.check_if_exists(_RETROARCH_BIN, system.config.emulator)
        self.check_if_exists(RETROARCH_CORES, system.config.emulator)

        gfx_backend = gfx_backend_get(system)
        video_shader, shader_bezel = self._resolve_shader(system, rom, gfx_backend)

        if 'configfile' not in system.config:
            system.config['configfile'] = str(RETROARCH_CFG)
            retroconfig = libretroConfig.open_unix_settings(RETROARCH_CFG)

            lightgun = system.config.get_bool('lightgun_map') if 'lightgun_map' in system.config else True
            libretroControllers.writeControllersConfig(retroconfig, system, playersControllers, lightgun)
            libretroConfig.writeLibretroConfigToFile(retroconfig, libretroConfig.rarch_custom_paths(system))

            bezel = system.config.get('bezel') or None
            if system.config.get_bool('force_no_bezel'):
                bezel = None

            libretroConfig.writeLibretroConfig(
                self, retroconfig, system, playersControllers, metadata, guns, wheels,
                rom, bezel, shader_bezel, gameResolution, gfx_backend
            )
            retroconfig.write()

            remapconfigDir = _RETROARCH_CFGDIR / "config" / "remaps" / "common"
            mkdir_if_not_exists(remapconfigDir)

        libretro_core = RETROARCH_CORES / f"{system.config.core}_libretro.so"
        info_file = RETROARCH_SHARE / f"{system.config.core}_libretro.info"

        if not info_file.exists() and not configure_emulator(rom):
            _logger.error("Core not found: %s", system.config.core)
            raise MissingCore

        dont_append_rom = configure_emulator(rom)
        if dont_append_rom:
            args_array = ["--config", RETROARCH_CFG]
        else:
            args_array = ["-L", libretro_core, "--config", RETROARCH_CFG]

        configToAppend: list[Path] = []
        custom_cfg = _RETROARCH_CFGDIR / f"{system.name}.cfg"
        if custom_cfg.is_file():
            configToAppend.append(custom_cfg)

        custom_game_cfg = _RETROARCH_CFGDIR / system.name / f"{rom.name}.cfg"
        if custom_game_cfg.is_file():
            configToAppend.append(custom_game_cfg)

        overlay_file = OVERLAYS / system.name / f"{rom.name}.cfg"
        if overlay_file.is_file():
            configToAppend.append(overlay_file)

        if video_shader is not None:
            args_array.extend(["--set-shader", video_shader])

        if configToAppend:
            args_array.extend(["--appendconfig", "|".join(str(c) for c in configToAppend)])

        if not dont_append_rom:
            args_array.append(rom)

        # Carga de savestate: si se especifica un slot y no es carga automática
        if (state_slot := system.config.get_str('state_slot')) and not system.config.get('state_filename', '.auto').endswith(".auto"):
            args_array.extend(["-e", state_slot])

        command_wrapper = [generate_bash_wrapper(
            system.config.emulator, _RETROARCH_BIN, args_array
        )]

        return Command.Command(array=command_wrapper, env={
            "XDG_CONFIG_HOME": _RETROARCH_XDG,
        })

    def _resolve_shader(self, system, rom, gfx_backend) -> tuple[Path | None, bool]:
        render_config = system.renderconfig
        alt_decoration = videoMode.get_alt_decoration(system.name, rom, 'retroarch')

        game_shader = None
        if alt_decoration == "0":
            if 'shader' in render_config:
                game_shader = render_config['shader']
        else:
            if 'shader-' + str(alt_decoration) in render_config:
                game_shader = render_config['shader-' + str(alt_decoration)]
            elif 'shader' in render_config:
                game_shader = render_config['shader']

        if 'shader' not in render_config or game_shader is None:
            return None, False

        shader_type = "slang" if gfx_backend in ('glcore', 'vulkan') else "glsl"
        shader_filename = f"{game_shader}.{shader_type}p"
        _logger.debug("searching shader %s", shader_filename)

        if (_SHADERS_DIR / shader_filename).exists():
            video_shader_dir = _SHADERS_DIR
        elif (RETROARCH_SHADERS / f"shaders_{shader_type}" / shader_filename).exists():
            video_shader_dir = RETROARCH_SHADERS / f"shaders_{shader_type}"
        else:
            video_shader_dir = RETROARCH_SHADERS

        video_shader = video_shader_dir / shader_filename
        shader_bezel = "noBezel" in video_shader.name
        return video_shader, shader_bezel


def _gfx_backend_check(backend: str):
    if backend == "vulkan" and vulkan.is_available():
        return "vulkan"
    if backend == "glcore" and videoMode.getGLVendor() in ["nvidia", "amd"] and videoMode.getGLVersion() >= 3.1:
        return "glcore"
    return "gl"


def gfx_backend_get(system: Emulator) -> str:
    retroconfig = UnixSettings(RETROARCH_CFG, separator=' ')
    backend = retroconfig.config.get('DEFAULT', 'video_driver', fallback=None)
    if backend:
        backend = backend.strip('"\'')
    if not backend:
        backend = retroconfig.config.get('DEFAULT', 'gfxbackend', fallback=None)
        if backend:
            backend = backend.strip('"\'')

    set_manually = bool(backend)
    if not backend:
        backend = "glcore"

    backend = _gfx_backend_check(backend)
    if backend == "opengl":
        backend = "gl"

    if not set_manually:
        core = system.config.core
        if backend in ["gl", "glcore"]:
            if backend == "gl" and core in ['kronos', 'mupen64plus-next', 'melonds', 'beetle-psx-hw']:
                backend = "glcore"
            if backend == "glcore" and core in ['parallel_n64', 'yabasanshiro', 'boom3']:
                backend = "gl"

    return backend