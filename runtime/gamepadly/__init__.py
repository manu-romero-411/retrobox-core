"""
gamepadly — Gamepad hotkey mapper para retrobox/batocera-fedora.

Uso como context manager desde configgen:

    from resources.utils.gamepadly import GamepadManager

    with GamepadManager(system, emulator, core, rom, controllers) as gm:
        launch_emulator(...)
    # al salir, los procesos mapper se terminan automáticamente
"""

from .gamepadly_manager import GamepadManager

__all__ = ["GamepadManager"]