from __future__ import annotations

import logging

from configgen.exceptions import RetroboxException
from runtime.launcher.configgen import Command
from runtime.retrobox_paths import SCREENSHOTS, configure_emulator, mkdir_if_not_exists
from ..Generator import Generator
from .ares_config import _ares_resolve_shader, write_ares_config
from .ares_paths import _ARES_LIBDIR, _ARES_SHADERS_DIR, _ARES_SHARE, ARES_BIN, _ARES_CFGDIR, _ARES_SAVES, _ARES_XDG

_logger = logging.getLogger(__name__)


class AresGenerator(Generator):
    def usesOpenGLDirectPreload(self, config) -> bool:
        return True

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        self.check_if_exists(ARES_BIN, system.config.emulator)
        self.check_if_exists(_ARES_SHARE, system.config.emulator)

        # Asegurar que la estructura de directorios de configuración y guardado existe
        mkdir_if_not_exists(_ARES_CFGDIR)
        mkdir_if_not_exists(_ARES_SAVES / system.name)
        mkdir_if_not_exists(SCREENSHOTS)

        # Generar o actualizar el fichero settings.bml antes de arrancar
        write_ares_config(system, playersControllers)


        command_array = [str(ARES_BIN)]
        args_array = []

        # shader must be loaded from cmdline.
        shader_cfg = system.renderconfig.get('shader')
        shader_final = _ares_resolve_shader(shader_cfg, _ARES_SHADERS_DIR)

        if shader_final != "None":
            args_array = ["--shader", shader_cfg]

        # kiosk mode disables the bottom bar.
        # pseudofullscreen allows for better window management on kde.
        args_array.extend([
            "--kiosk",
            "--pseudofullscreen",  
        ])

        if not configure_emulator(rom):
            args_array.append(str(rom))
            command_array.extend(args_array)

        env = {
            "XDG_DATA_HOME": str(_ARES_XDG),
            "XDG_CONFIG_HOME": str(_ARES_XDG),
            "LD_LIBRARY_PATH": str(_ARES_LIBDIR),
        }

        return Command.Command(array=command_array, env=env)