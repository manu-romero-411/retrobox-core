"""
runtime.paths — punto de entrada único de paths y constantes de
Retrobox.

Internamente dividido por subsistema:
    _base.py       -> genérico (XDG, ROOTDIR, bootstrap de .env, helpers de FS)
    _configgen.py  -> configgen / emulatorlauncher / launcher
    _frontend.py   -> EmulationStation (runtime/startup/frontend_conf)
    _gamepadly.py  -> las 4 constantes que necesita emulatorlauncher.py
                      para instanciar GamepadManager (gamepadly ya no
                      importa nada de aquí directamente)

Pero de puertas afuera nada cambia: todo se sigue importando igual que
antes, `from runtime.paths import X`. Ninguno de los ~100
archivos que ya hacen ese import necesita tocarse.

Si añades una constante nueva, decide primero de qué subsistema es y
créala en el _archivo.py correspondiente (o crea uno nuevo si es de un
subsistema distinto) — y luego añádela aquí. No la definas directamente
en este __init__.py.
"""

from __future__ import annotations

from ._base import (
    CACHE,
    CONF_INIT,
    DATAINIT_DIR,
    DEFAULTS_DIR,
    EMULATORS,
    ENV_FILE,
    HOME_INIT,
    HOOKS,
    LOGS,
    RESOURCES_DIR,
    RETROBOX_ROOTDIR,
    ROMS,
    USERDATA,
    _SYSTEM_LOCAL_BIN,
    _SYSTEM_LOCAL_SHARE,
    _USER_HOME,
    _XDG_CACHE,
    _XDG_CONFIG,
    _XDG_DATA,
    check_env_dirs,
    ensure_parents_and_open,
    ensure_symlink,
    mkdir_if_not_exists,
)
from ._configgen import (
    BIOS,
    CHEATS,
    CMDFILES_DIR,
    GUN_OVERLAYS_DIR,
    HUD_CONFIG_FILE,
    MAME_ARTWORK_DIR,
    MAME_SOFTWARE_DIR,
    OVERLAY_BASE_DIR,
    OVERLAYS,
    RECORDINGS,
    ROTATION_FILE,
    RUNTIME_DIR,
    SAVES,
    SCREENSHOTS,
    SHADER_BEZELS_DIR,
    SQUASHFS_DIR,
    _DECORATIONS_DEF_DIR,
    _DECORATIONS_DIR,
    EMU_FEATURES_DIR,
    NVIDIA_POWERD_SCRIPT,
    _SHADERS_DEF_DIR,
    _SHADERS_DIR,
    _SYSTEM_SCRIPTS,
    SYSTEMS_CONF_DIR,
    UTILS_DIR,
    configure_emulator,
)
from ._frontend import (
    ES_EXECUTABLE,
    ES_FEATURES_CFG,
    ES_FEATURES_TMP,
    ES_GAMES_METADATA,
    ES_GUNS_ART_METADATA,
    ES_GUNS_METADATA,
    ES_INI_CFG,
    ES_INI_TMP,
    ES_INPUT_CFG,
    ES_SETTINGS_CFG,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
    ES_WHEELS_METADATA,
    _ES_RESOURCES_DIR,
    FRONTEND_DIR,
    _USER_ES_DIR,
)
from ._gamepadly import (
    GAMEPADLY_MAPPER,
    _GAMEPADLY_DIR,
    _GAMEPADLY_PROFILES,
    _GAMEPADLY_USER_PROFILES,
)

# API pública "de verdad" (sin los nombres con guion bajo, que se
# mantienen importables por compatibilidad pero no deberían usarse en
# código nuevo fuera de configgen/frontend_conf existente).
__all__ = [
    # _base
    "CACHE",
    "CONF_INIT",
    "DATAINIT_DIR",
    "DEFAULTS_DIR",
    "EMULATORS",
    "ENV_FILE",
    "HOME_INIT",
    "HOOKS",
    "LOGS",
    "RESOURCES_DIR",
    "RETROBOX_ROOTDIR",
    "ROMS",
    "USERDATA",
    "check_env_dirs",
    "ensure_parents_and_open",
    "ensure_symlink",
    "mkdir_if_not_exists",
    # _configgen
    "BIOS",
    "CHEATS",
    "CMDFILES_DIR",
    "GUN_OVERLAYS_DIR",
    "HUD_CONFIG_FILE",
    "MAME_ARTWORK_DIR",
    "MAME_SOFTWARE_DIR",
    "OVERLAY_BASE_DIR",
    "OVERLAYS",
    "RECORDINGS",
    "ROTATION_FILE",
    "RUNTIME_DIR",
    "SAVES",
    "SCREENSHOTS",
    "SHADER_BEZELS_DIR",
    "SQUASHFS_DIR",
    "configure_emulator",
    # _frontend
    "ES_EXECUTABLE",
    "ES_FEATURES_CFG",
    "ES_FEATURES_TMP",
    "ES_GAMES_METADATA",
    "ES_GUNS_ART_METADATA",
    "ES_GUNS_METADATA",
    "ES_INI_CFG",
    "ES_INI_TMP",
    "ES_INPUT_CFG",
    "ES_SETTINGS_CFG",
    "ES_SYSTEMS_CFG",
    "ES_SYSTEMS_TMP",
    "ES_WHEELS_METADATA",
    # _gamepadly
    "GAMEPADLY_MAPPER",
]