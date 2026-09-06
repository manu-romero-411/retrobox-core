from __future__ import annotations

import logging
from struct import pack, unpack
from typing import TYPE_CHECKING, BinaryIO

from ...utils.configparser import CaseSensitiveConfigParser
from ...utils import vulkan
from runtime.paths import BIOS, ROMS, SAVES, mkdir_if_not_exists
from .dolphin_paths import (
    _DOLPHIN_CFGDIR,
    _DOLPHIN_GC_CARD_A,
    _DOLPHIN_GC_CARD_B,
    _DOLPHIN_WII_NAND,
    _DOLPHIN_WII_RESPACKS,
    _DOLPHIN_WII_SDCARD_DIR,
    _DOLPHIN_WII_SDCARD_SYNC,
    _DOLPHIN_WII_WFSDIR,
    DOLPHIN_GFX_INI,
    DOLPHIN_INI,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ...batoceraTypes import DeviceInfoMapping, Resolution
    from ...config import SystemConfig
    from ...controller import Controllers
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# dolphin.ini
#
# Only the options batocera needs to *function* (paths pointing to batocera's
# storage layout) or that map to explicit batocera settings (controller port
# type, rendering backend, discord rpc) are written here. Everything else
# (audio backend, cheats, dual core, panic handlers, on-screen messages,
# confirm-on-stop, IPL skip, GC language, MMU, wiimote scanning...) is left
# untouched so choices made from within Dolphin's own UI persist.
# ---------------------------------------------------------------------------

def write_dolphin_ini(system: Emulator, playersControllers: Controllers, wheels: DeviceInfoMapping) -> None:
    mkdir_if_not_exists(DOLPHIN_INI.parent)

    dolphinSettings = CaseSensitiveConfigParser(interpolation=None)
    if DOLPHIN_INI.exists():
        dolphinSettings.read(DOLPHIN_INI)

    for section in ("General", "Core", "GBA"):
        if not dolphinSettings.has_section(section):
            dolphinSettings.add_section(section)

    _configure_paths(dolphinSettings)
    _configure_discord_rpc(dolphinSettings, system)
    configure_gfx_backend(dolphinSettings, system)
    configure_controller_ports(dolphinSettings, system, playersControllers, wheels)

    with DOLPHIN_INI.open('w') as configfile:
        dolphinSettings.write(configfile)


def _configure_paths(dolphinSettings: CaseSensitiveConfigParser) -> None:
    # Default games path (only set once, so the user can still change it from Dolphin's UI)
    if "ISOPaths" not in dolphinSettings["General"]:
        dolphinSettings.set("General", "ISOPath0", f"{ROMS}/wii")
        dolphinSettings.set("General", "ISOPath1", f"{ROMS}/gamecube")
        dolphinSettings.set("General", "ISOPaths", "2")

    mkdir_if_not_exists(_DOLPHIN_WII_NAND)
    mkdir_if_not_exists(_DOLPHIN_WII_RESPACKS)
    mkdir_if_not_exists(_DOLPHIN_WII_WFSDIR)
    mkdir_if_not_exists(_DOLPHIN_WII_SDCARD_DIR)
    mkdir_if_not_exists(_DOLPHIN_WII_SDCARD_SYNC)
    mkdir_if_not_exists(_DOLPHIN_GC_CARD_A)
    mkdir_if_not_exists(_DOLPHIN_GC_CARD_B)
    mkdir_if_not_exists(SAVES / "gba" / "dolphin_emu")

    dolphinSettings.set("General", "DumpPath", str(_DOLPHIN_CFGDIR / "Dump/"))
    dolphinSettings.set("General", "LoadPath", str(_DOLPHIN_CFGDIR / "Load/"))
    dolphinSettings.set("General", "NANDRootPath", str(_DOLPHIN_WII_NAND))
    dolphinSettings.set("General", "ResourcePackPath", str(_DOLPHIN_WII_RESPACKS))
    dolphinSettings.set("General", "WFSPath", str(_DOLPHIN_WII_WFSDIR))
    dolphinSettings.set("General", "WiiSDCardPath", str(_DOLPHIN_WII_SDCARD_DIR / "WiiSD.raw"))
    dolphinSettings.set("General", "WiiSDCardSyncFolder", str(_DOLPHIN_WII_SDCARD_SYNC))

    dolphinSettings.set("Core", "GCIFolderAPath", str(_DOLPHIN_GC_CARD_A))
    dolphinSettings.set("Core", "GCIFolderBPath", str(_DOLPHIN_GC_CARD_B))

    dolphinSettings.set("GBA", "BIOS", str(BIOS / "gba_bios.bin"))
    dolphinSettings.set("GBA", "SavesPath", str(SAVES / "gba" / "dolphin_emu"))


def _configure_discord_rpc(dolphinSettings: CaseSensitiveConfigParser, system: Emulator) -> None:
    dolphinSettings.set("General", "UseDiscordPresence", str(system.config.get_bool('discordrpc', False)))


def configure_gfx_backend(dolphinSettings: CaseSensitiveConfigParser, system: Emulator) -> None:
    if system.config.get("gfxbackend", "Vulkan") == "Vulkan":
        dolphinSettings.set("Core", "GFXBackend", "Vulkan")
        if not vulkan.is_available():
            _logger.debug("Vulkan driver is not available on the system. Using OpenGL instead.")
            dolphinSettings.set("Core", "GFXBackend", "OGL")
    else:
        dolphinSettings.set("Core", "GFXBackend", "OGL")


def configure_controller_ports(dolphinSettings: CaseSensitiveConfigParser, system: Emulator, playersControllers: Controllers, wheels: DeviceInfoMapping) -> None:
    for i in range(4):
        key = f"dolphin_port_{i+1}_type"
        if value := system.config.get(key):
            # 6a/6b both map to "Standard Controller" (6); the a/b split only
            # differentiates button layout, handled in dolphinControllers.
            value = "6" if value in ["6a", "6b"] else value
            dolphinSettings.set("Core", f"SIDevice{i}", value)
        else:
            if system.name == "gamecube" and system.config.use_wheels and wheels and i < len(playersControllers) and playersControllers[i].device_path in wheels:
                dolphinSettings.set("Core", f"SIDevice{i}", "8")
            else:
                dolphinSettings.set("Core", f"SIDevice{i}", "6")

    # Triforce wheel: both ports must be GC Steering (8) for baseboard detection.
    if system.name == "triforce" and system.config.use_wheels and wheels:
        if not system.config.get("dolphin_port_1_type"):
            dolphinSettings.set("Core", "SIDevice0", "8")
        if not system.config.get("dolphin_port_2_type"):
            dolphinSettings.set("Core", "SIDevice1", "8")


# ---------------------------------------------------------------------------
# gfx.ini
#
# Only aspect ratio, the scaling multiplier (internal resolution) and the
# GPU picked for the Vulkan backend are managed here. All other graphics
# tweaks (FPS counter, hires textures, ubershaders, AA, anisotropic
# filtering, VSync, perf hacks...) are left to Dolphin's graphics settings.
# ---------------------------------------------------------------------------

def write_gfx_ini(system: Emulator) -> None:
    dolphinGFXSettings = CaseSensitiveConfigParser(interpolation=None)
    dolphinGFXSettings.read(DOLPHIN_GFX_INI)

    if not dolphinGFXSettings.has_section("Settings"):
        dolphinGFXSettings.add_section("Settings")
    if not dolphinGFXSettings.has_section("Hardware"):
        dolphinGFXSettings.add_section("Hardware")

    _configure_gpu_adapter(dolphinGFXSettings)

    # Aspect Ratio: 0 Auto / 1 Force 16:9 / 2 Force 4:3 / 3 Stretch
    dolphinGFXSettings.set("Settings", "AspectRatio", system.config.get("dolphin_aspect_ratio", "0"))

    # Widescreen hack, needed to actually get 16:9 out of GameCube titles
    # that don't support it natively when aspect ratio is forced/auto'd to 16:9.
    dolphinGFXSettings.set("Settings", "wideScreenHack", str(system.config.get_bool('widescreen_hack')))

    # Internal resolution / scaling multiplier (1 = native, 2 = 2x, ...)
    dolphinGFXSettings.set("Settings", "InternalResolution", system.config.get("internal_resolution", "1"))

    with DOLPHIN_GFX_INI.open('w') as configfile:
        dolphinGFXSettings.write(configfile)


def _configure_gpu_adapter(dolphinGFXSettings: CaseSensitiveConfigParser) -> None:
    if vulkan.is_available():
        _logger.debug("Vulkan driver is available on the system.")
        if vulkan.has_discrete_gpu():
            _logger.debug("A discrete GPU is available on the system. We will use that for performance")
            discrete_index = vulkan.get_discrete_gpu_index()
            if discrete_index:
                _logger.debug("Using Discrete GPU Index: %s for Dolphin", discrete_index)
                dolphinGFXSettings.set("Hardware", "Adapter", discrete_index)
            else:
                _logger.debug("Couldn't get discrete GPU index")
        else:
            _logger.debug("Discrete GPU is not available on the system. Using default.")


# ---------------------------------------------------------------------------
# Hotkeys.ini - overwritten in full each launch, as before
# ---------------------------------------------------------------------------

def write_hotkeys_ini() -> None:
    hotkeyConfig = CaseSensitiveConfigParser(interpolation=None)
    hotkeyConfig.add_section('Hotkeys')
    hotkeyConfig.set('Hotkeys', 'Device', 'XInput2/0/Virtual core pointer')
    hotkeyConfig.set('Hotkeys', 'General/Open', '@(Ctrl+O)')
    hotkeyConfig.set('Hotkeys', 'General/Toggle Pause', 'F10')
    hotkeyConfig.set('Hotkeys', 'General/Stop', 'Escape')
    hotkeyConfig.set('Hotkeys', 'General/Toggle Fullscreen', '@(Alt+Return)')
    hotkeyConfig.set('Hotkeys', 'General/Take Screenshot', 'F9')
    hotkeyConfig.set('Hotkeys', 'General/Exit', '@(Shift+F11)')
    hotkeyConfig.set('Hotkeys', 'Emulation Speed/Disable Emulation Speed Limit', 'Tab')
    hotkeyConfig.set('Hotkeys', 'Stepping/Step Into', 'F11')
    hotkeyConfig.set('Hotkeys', 'Stepping/Step Over', '@(Shift+F10)')
    hotkeyConfig.set('Hotkeys', 'Stepping/Step Out', '@(Shift+F11)')
    hotkeyConfig.set('Hotkeys', 'Breakpoint/Toggle Breakpoint', '@(Shift+F9)')
    hotkeyConfig.set('Hotkeys', 'Wii/Connect Wii Remote 1', '@(Alt+F5)')
    hotkeyConfig.set('Hotkeys', 'Wii/Connect Wii Remote 2', '@(Alt+F6)')
    hotkeyConfig.set('Hotkeys', 'Wii/Connect Wii Remote 3', '@(Alt+F7)')
    hotkeyConfig.set('Hotkeys', 'Wii/Connect Wii Remote 4', '@(Alt+F8)')
    hotkeyConfig.set('Hotkeys', 'Wii/Connect Balance Board', '@(Alt+F9)')
    hotkeyConfig.set('Hotkeys', 'Other State Hotkeys/Increase Selected State Slot', '@(Shift+F1)')
    hotkeyConfig.set('Hotkeys', 'Other State Hotkeys/Decrease Selected State Slot', '@(Shift+F2)')
    hotkeyConfig.set('Hotkeys', 'Load State/Load from Selected Slot', 'F8')
    hotkeyConfig.set('Hotkeys', 'Save State/Save to Selected Slot', 'F5')
    hotkeyConfig.set('Hotkeys', 'Other State Hotkeys/Undo Load State', '@(Shift+F12)')
    hotkeyConfig.set('Hotkeys', 'GBA Core/Load ROM', '@(`Ctrl`+`Shift`+`O`)')
    hotkeyConfig.set('Hotkeys', 'GBA Core/Unload ROM', '@(`Ctrl`+`Shift`+`W`)')
    hotkeyConfig.set('Hotkeys', 'GBA Core/Reset', '@(`Ctrl`+`Shift`+`R`)')
    hotkeyConfig.set('Hotkeys', 'GBA Volume/Volume Down', '`KP_Subtract`')
    hotkeyConfig.set('Hotkeys', 'GBA Volume/Volume Up', '`KP_Add`')
    hotkeyConfig.set('Hotkeys', 'GBA Volume/Volume Toggle Mute', '`M`')
    hotkeyConfig.set('Hotkeys', 'GBA Window Size/1x', '`KP_1`')
    hotkeyConfig.set('Hotkeys', 'GBA Window Size/2x', '`KP_2`')
    hotkeyConfig.set('Hotkeys', 'GBA Window Size/3x', '`KP_3`')
    hotkeyConfig.set('Hotkeys', 'GBA Window Size/4x', '`KP_4`')
    hotkeyConfig.set('Hotkeys', 'USB Emulation Devices/Show Skylanders Portal', '@(Ctrl+P)')
    hotkeyConfig.set('Hotkeys', 'USB Emulation Devices/Show Infinity Base', '@(Ctrl+I)')

    with (_DOLPHIN_CFGDIR / 'Hotkeys.ini').open('w') as configfile:
        hotkeyConfig.write(configfile)


# ---------------------------------------------------------------------------
# SYSCONF - only the Wii's internal aspect-ratio flag (IPL.AR) is kept in
# sync with batocera's aspect ratio setting. Language and sensor bar
# position are left as Wii-menu-level settings.
# ---------------------------------------------------------------------------

def _readBEInt16(f: BinaryIO) -> int:
    return unpack(">H", f.read(2))[0]

def _readBEInt32(f: BinaryIO) -> int:
    return unpack(">L", f.read(4))[0]

def _readString(f: BinaryIO, x: int) -> str:
    return f.read(x).decode('utf-8')

def _readInt8(f: BinaryIO) -> int:
    return unpack("B", f.read(1))[0]

def _writeInt8(f: BinaryIO, x: int) -> None:
    f.write(pack("B", x))

def _readWriteEntry(f: BinaryIO, setval: Mapping[str, int]) -> None:
    itemHeader     = _readInt8(f)
    itemType       = (itemHeader & 0xe0) >> 5
    itemNameLength = (itemHeader & 0x1f) + 1
    itemName       = _readString(f, itemNameLength)

    if itemName in setval:
        if itemType == 3:  # byte
            _writeInt8(f, setval[itemName])
        else:
            raise Exception(f"not writable type {itemType}")
    else:
        if itemType == 1:      # big array
            f.read(_readBEInt16(f) + 1)
        elif itemType == 2:    # small array
            f.read(_readInt8(f) + 1)
        elif itemType == 3:    # byte
            _readInt8(f)
        elif itemType == 4:    # short
            _readBEInt16(f)
        elif itemType == 5:    # long
            _readBEInt32(f)
        elif itemType == 6:    # long long
            f.read(8)
        elif itemType == 7:    # bool
            _readInt8(f)
        else:
            raise Exception(f"unknown type {itemType}")


def get_ratio_from_config(config: SystemConfig) -> int:
    # Wii-internal flag: 0: 4:3 ; 1: 16:9
    return 1 if config.get('tv_mode') == '1' else 0


def update_sysconf_aspect_ratio(config: SystemConfig, filepath: Path, gameResolution: Resolution | None = None) -> None:
    if not filepath.exists():
        return

    setval = {"IPL.AR": get_ratio_from_config(config)}

    try:
        with filepath.open("r+b") as f:
            _readString(f, 4)  # "SCv0" header
            numEntries = _readBEInt16(f)
            f.read((numEntries + 1) * 2)  # offsets table
            for _ in range(numEntries):
                _readWriteEntry(f, setval)
    except Exception:
        _logger.warning("Couldn't update the SYSCONF aspect ratio flag", exc_info=True)


# ---------------------------------------------------------------------------
# In-game ratio (used by batocera for bezels/screenscraper, not by Dolphin
# itself). Mirrors the AspectRatio + Wii tv-mode logic above.
# ---------------------------------------------------------------------------

def get_in_game_ratio(config: SystemConfig, gameResolution: Resolution) -> float:
    dolphinGFXSettings = CaseSensitiveConfigParser(interpolation=None)
    dolphinGFXSettings.read(DOLPHIN_GFX_INI)
    dolphin_aspect_ratio = dolphinGFXSettings.get("Settings", "AspectRatio", fallback="0")

    wii_tv_mode = config.get_bool('widescreen_hack', return_values=(1, 0))
    try:
        wii_tv_mode = get_ratio_from_config(config)
    except Exception:
        pass

    # Auto
    if dolphin_aspect_ratio == "0":
        return 16 / 9 if wii_tv_mode == 1 else 4 / 3
    # Forced 16:9
    if dolphin_aspect_ratio == "1":
        return 16 / 9
    # Forced 4:3
    if dolphin_aspect_ratio == "2":
        return 4 / 3
    # Stretched (depends on physical screen geometry)
    if dolphin_aspect_ratio == "3":
        return gameResolution["width"] / gameResolution["height"]

    return 4 / 3