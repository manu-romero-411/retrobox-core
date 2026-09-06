import logging
import shutil
from pathlib import Path
from typing import Mapping

from configgen.generators.pcsx2.pcsx2_controllers import _pcsx2_gen_controllers_config

from ...Emulator import Emulator
from ...batoceraTypes import DeviceInfoMapping, Resolution
from ...config import SystemConfig
from ...controller import Controllers
from ...exceptions import RetroboxException
from .pcsx2_paths import _PCSX2_BIOS, _PCSX2_CFGDIR, PCSX2_CFG, _PCSX2_TEXTURES
from ...gun import Guns
from ...input import Input
from ...utils import vulkan
from ...utils.configparser import CaseSensitiveConfigParser
from runtime.paths import CACHE, CHEATS, LOGS, ROMS, SAVES, SCREENSHOTS, ensure_parents_and_open, mkdir_if_not_exists

_logger = logging.getLogger(__name__)


def getGfxRatioFromConfig(config: SystemConfig, gameResolution: Resolution):
    # 2: 4:3 ; 1: 16:9
    ratio = config.get("pcsx2_ratio")
    if ratio == "16:9":
        return "16:9"
    if ratio == "full":
        return "Stretch"
    return "4:3"

def configureReg(config_directory: Path) -> None:
    with ensure_parents_and_open(config_directory / "PCSX2-reg.ini", "w") as f:
        f.write("DocumentsFolderMode=User\n")
        f.write(f"CustomDocumentsFolder={_PCSX2_CFGDIR}\n")
        f.write("UseDefaultSettingsFolder=enabled\n")
        f.write(f"SettingsFolder={config_directory / 'inis'}\n")
        f.write(f"Install_Dir={_PCSX2_CFGDIR}\n")
        f.write("RunWizard=0\n")

def configureAudio(config_directory: Path) -> None:
    configFileName = config_directory / 'inis' / "spu2-x.ini"
    mkdir_if_not_exists(configFileName.parent)

    # Keep the custom files
    if configFileName.exists():
        return

    f = configFileName.open("w")
    f.write("[MIXING]\n")
    f.write("Interpolation=1\n")
    f.write("Disable_Effects=0\n")
    f.write("[OUTPUT]\n")
    f.write("Output_Module=SDLAudio\n")
    f.write("[PORTAUDIO]\n")
    f.write("HostApi=ALSA\n")
    f.write("Device=default\n")
    f.write("[SDL]\n")
    f.write("HostApi=alsa\n")
    f.close()

def configureINI(
        system: Emulator,
        controllers: Controllers,
        metadata: Mapping[str, str],
        guns: Guns,
        wheels: DeviceInfoMapping,
        playingWithWheel: bool
    ) -> None:

    mkdir_if_not_exists(PCSX2_CFG.parent)

    if not PCSX2_CFG.is_file():
        with PCSX2_CFG.open("w") as f:
            f.write("[UI]\n")

    pcsx2_iniconfig = CaseSensitiveConfigParser(interpolation=None)

    if PCSX2_CFG.is_file():
        pcsx2_iniconfig.read(PCSX2_CFG)

    ## [Folders]
    if not pcsx2_iniconfig.has_section("Folders"):
        pcsx2_iniconfig.add_section("Folders")

    # remove inconsistent SaveStates casing if it exists
    pcsx2_iniconfig.remove_option("Folders", "SaveStates")

    # set the folders we want
    pcsx2_iniconfig.set("Folders", "Bios",          str(_PCSX2_BIOS))
    pcsx2_iniconfig.set("Folders", "Snapshots",     str(SCREENSHOTS))
    pcsx2_iniconfig.set("Folders", "Savestates",    str(SAVES / "ps2" / "sstates"))
    pcsx2_iniconfig.set("Folders", "MemoryCards",   str(SAVES / "ps2" / "memcards"))
    pcsx2_iniconfig.set("Folders", "Logs",          str(LOGS))
    pcsx2_iniconfig.set("Folders", "Cheats",        str(CHEATS / "ps2"))
    pcsx2_iniconfig.set("Folders", "Cache",         str(CACHE / "ps2"))
    pcsx2_iniconfig.set("Folders", "Textures",      str(_PCSX2_CFGDIR / "textures"))
    pcsx2_iniconfig.set("Folders", "InputProfiles", str(_PCSX2_CFGDIR / "inputprofiles"))
    pcsx2_iniconfig.set("Folders", "Videos",        str(SAVES / "ps2" / "videos"))
    # create cache folder
    mkdir_if_not_exists(CACHE / "ps2")

    ## [Filenames] - BIOS selection
    if not pcsx2_iniconfig.has_section("Filenames"):
        pcsx2_iniconfig.add_section("Filenames")

    # abort execution if bios file is not found
    bios_file = system.config.get("pcsx2_forcebios", "ps2-0230e-20080220.bin")
    if not Path(f"{_PCSX2_BIOS}/{bios_file}").is_file():
        raise RetroboxException(
            f'PS2 BIOS not found: {system.config.get("pcsx2_forcebios")}')

    # set bios file
    pcsx2_iniconfig.set("Filenames", "BIOS", bios_file)

    ## [EmuCore]
    if not pcsx2_iniconfig.has_section("EmuCore"):
        pcsx2_iniconfig.add_section("EmuCore")

    # Discord rich presence
    pcsx2_iniconfig.set("EmuCore", "EnableDiscordPresence", system.config.get_bool('discordrpc', False, return_values=("true", "false")))

    # Fastboot
    pcsx2_iniconfig.set("EmuCore", "EnableFastBoot", system.config.get_bool('pcsx2_fastboot', True, return_values=("false", "true")))

    ## [EmuCore/GS] - renderer, aspect ratio and scaling
    if not pcsx2_iniconfig.has_section("EmuCore/GS"):
        pcsx2_iniconfig.add_section("EmuCore/GS")

    # Renderer
    # Check Vulkan first to be sure
    if vulkan.is_available():
        _logger.debug("Vulkan driver is available on the system.")
        renderer = "-1"

        if gfxbackend := system.config.get("pcsx2_gfxbackend", "14"):
            if gfxbackend == "12":
                _logger.debug("User selected OpenGL")
            if gfxbackend == "13":
                _logger.debug("User selected Software! Man you must have a fast CPU!")
            elif gfxbackend == "14":
                _logger.debug("User selected Vulkan")
                if vulkan.has_discrete_gpu():
                    _logger.debug("A discrete GPU is available on the system. We will use that for performance")
                    discrete_name = vulkan.get_discrete_gpu_name()
                    if discrete_name:
                        _logger.debug("Using Discrete GPU Name: %s for PCSX2", discrete_name)
                        pcsx2_iniconfig.set("EmuCore/GS", "Adapter", discrete_name)
                    else:
                        _logger.debug("Couldn't get discrete GPU Name")
                        pcsx2_iniconfig.set("EmuCore/GS", "Adapter", "(Default)")
                else:
                    _logger.debug("Discrete GPU is not available on the system. Using default.")
                    pcsx2_iniconfig.set("EmuCore/GS", "Adapter", "(Default)")
            renderer = gfxbackend
        else:
            _logger.debug("User selected to Automatic")

        pcsx2_iniconfig.set("EmuCore/GS", "Renderer", renderer)
    else:
        _logger.debug("Vulkan driver is not available on the system. Falling back to Automatic")
        pcsx2_iniconfig.set("EmuCore/GS", "Renderer", "-1")

    # Aspect ratio
    pcsx2_iniconfig.set("EmuCore/GS", "AspectRatio", system.config.get("pcsx2_ratio", "Auto 4:3/3:2"))
    pcsx2_iniconfig.set("EmuCore/GS", "FMVAspectRatioSwitch", system.config.get("pcsx2_fmv_ratio", "Auto 4:3/3:2"))

    # Scaling
    pcsx2_iniconfig.set("EmuCore/GS", "upscale_multiplier", system.config.get("pcsx2_resolution", "1"))
    pcsx2_iniconfig.set("EmuCore/GS", "IntegerScaling", system.config.get("pcsx2_scaling", "false"))

    ## [InputSources]
    if not pcsx2_iniconfig.has_section("InputSources"):
        pcsx2_iniconfig.add_section("InputSources")

    pcsx2_iniconfig.set("InputSources", "Keyboard", "true")
    pcsx2_iniconfig.set("InputSources", "Mouse", "true")
    pcsx2_iniconfig.set("InputSources", "SDL", "true")

    ## [Hotkeys]
    if not pcsx2_iniconfig.has_section("Hotkeys"):
        pcsx2_iniconfig.add_section("Hotkeys")

    pcsx2_iniconfig.set("Hotkeys", "ToggleFullscreen", "Keyboard/Alt & Keyboard/Return")
    pcsx2_iniconfig.set("Hotkeys", "CycleAspectRatio", "Keyboard/F6")
    pcsx2_iniconfig.set("Hotkeys", "CycleInterlaceMode", "Keyboard/F5")
    pcsx2_iniconfig.set("Hotkeys", "CycleMipmapMode", "Keyboard/Insert")
    pcsx2_iniconfig.set("Hotkeys", "GSDumpMultiFrame", "Keyboard/Control & Keyboard/Shift & Keyboard/F8")
    pcsx2_iniconfig.set("Hotkeys", "Screenshot", "Keyboard/F8")
    pcsx2_iniconfig.set("Hotkeys", "GSDumpSingleFrame", "Keyboard/Shift & Keyboard/F8")
    pcsx2_iniconfig.set("Hotkeys", "ToggleSoftwareRendering", "Keyboard/F9")
    pcsx2_iniconfig.set("Hotkeys", "ZoomIn", "Keyboard/Control & Keyboard/Plus")
    pcsx2_iniconfig.set("Hotkeys", "ZoomOut", "Keyboard/Control & Keyboard/Minus")
    pcsx2_iniconfig.set("Hotkeys", "InputRecToggleMode", "Keyboard/Shift & Keyboard/R")
    pcsx2_iniconfig.set("Hotkeys", "LoadStateFromSlot", "Keyboard/F3")
    pcsx2_iniconfig.set("Hotkeys", "SaveStateToSlot", "Keyboard/F1")
    pcsx2_iniconfig.set("Hotkeys", "NextSaveStateSlot", "Keyboard/F2")
    pcsx2_iniconfig.set("Hotkeys", "PreviousSaveStateSlot", "Keyboard/Shift & Keyboard/F2")
    pcsx2_iniconfig.set("Hotkeys", "OpenPauseMenu", "Keyboard/Escape")
    pcsx2_iniconfig.set("Hotkeys", "ToggleFrameLimit", "Keyboard/F4")
    pcsx2_iniconfig.set("Hotkeys", "TogglePause", "Keyboard/Space")
    pcsx2_iniconfig.set("Hotkeys", "ToggleSlowMotion", "Keyboard/Shift & Keyboard/Backtab")
    pcsx2_iniconfig.set("Hotkeys", "ToggleTurbo", "Keyboard/Tab")
    pcsx2_iniconfig.set("Hotkeys", "HoldTurbo", "Keyboard/Period")

    # clean gun sections
    if pcsx2_iniconfig.has_section("USB1") and pcsx2_iniconfig.has_option("USB1", "Type") and pcsx2_iniconfig.get("USB1", "Type") == "guncon2":
        pcsx2_iniconfig.remove_option("USB1", "Type")
    if pcsx2_iniconfig.has_section("USB2") and pcsx2_iniconfig.has_option("USB2", "Type") and pcsx2_iniconfig.get("USB2", "Type") == "guncon2":
        pcsx2_iniconfig.remove_option("USB2", "Type")
    if pcsx2_iniconfig.has_section("USB1") and pcsx2_iniconfig.has_option("USB1", "guncon2_Start"):
        pcsx2_iniconfig.remove_option("USB1", "guncon2_Start")
    if pcsx2_iniconfig.has_section("USB2") and pcsx2_iniconfig.has_option("USB2", "guncon2_Start"):
        pcsx2_iniconfig.remove_option("USB2", "guncon2_Start")
    if pcsx2_iniconfig.has_section("USB1") and pcsx2_iniconfig.has_option("USB1", "guncon2_C"):
        pcsx2_iniconfig.remove_option("USB1", "guncon2_C")
    if pcsx2_iniconfig.has_section("USB2") and pcsx2_iniconfig.has_option("USB2", "guncon2_C"):
        pcsx2_iniconfig.remove_option("USB2", "guncon2_C")
    if pcsx2_iniconfig.has_section("USB1") and pcsx2_iniconfig.has_option("USB1", "guncon2_numdevice"):
        pcsx2_iniconfig.remove_option("USB1", "guncon2_numdevice")
    if pcsx2_iniconfig.has_section("USB2") and pcsx2_iniconfig.has_option("USB2", "guncon2_numdevice"):
        pcsx2_iniconfig.remove_option("USB2", "guncon2_numdevice")

    # clean wheel sections
    if pcsx2_iniconfig.has_section("USB1") and pcsx2_iniconfig.has_option("USB1", "Type") and pcsx2_iniconfig.get("USB1", "Type") == "Pad" and pcsx2_iniconfig.has_option("USB1", "Pad_subtype") and pcsx2_iniconfig.get("USB1", "Pad_subtype") == "1":
        pcsx2_iniconfig.remove_option("USB1", "Type")
    if pcsx2_iniconfig.has_section("USB2") and pcsx2_iniconfig.has_option("USB2", "Type") and pcsx2_iniconfig.get("USB2", "Type") == "Pad" and pcsx2_iniconfig.has_option("USB2", "Pad_subtype") and pcsx2_iniconfig.get("USB2", "Pad_subtype") == "1":
        pcsx2_iniconfig.remove_option("USB2", "Type")

    # guns
    if system.config.use_guns and guns:
        gun1onport2 = len(guns) == 1 and "gun_gun1port" in metadata and metadata["gun_gun1port"] == "2"
        pedalsKeys = {1: "c", 2: "v", 3: "b", 4: "n"}

        if guns and not gun1onport2:
            if not pcsx2_iniconfig.has_section("USB1"):
                pcsx2_iniconfig.add_section("USB1")
            pcsx2_iniconfig.set("USB1", "Type", "guncon2")
            for nc, pad in enumerate(controllers, start=1):
                if nc == 1 and not gun1onport2 and "start" in pad.inputs:
                    pcsx2_iniconfig.set("USB1", "guncon2_Start", f"SDL-{pad.index}/Start")

            # find a keyboard key to simulate the action of the player (always like button 2); search in batocera.conf, else default config
            pedalkey = system.config.get("controllers.pedals1", pedalsKeys[1])
            pcsx2_iniconfig.set("USB1", "guncon2_C", f"Keyboard/{pedalkey.upper()}")

        if len(guns) >= 2 or gun1onport2:
            if not pcsx2_iniconfig.has_section("USB2"):
                pcsx2_iniconfig.add_section("USB2")
            pcsx2_iniconfig.set("USB2", "Type", "guncon2")
            for nc, pad in enumerate(controllers, start=1):
                if (nc == 2 or gun1onport2) and "start" in pad.inputs:
                    pcsx2_iniconfig.set("USB2", "guncon2_Start", f"SDL-{pad.index}/Start")

            # find a keyboard key to simulate the action of the player (always like button 2); search in batocera.conf, else default config
            pedalkey = system.config.get("controllers.pedals2", pedalsKeys[2])
            pcsx2_iniconfig.set("USB2", "guncon2_C", f"Keyboard/{pedalkey.upper()}")

            if gun1onport2:
                pcsx2_iniconfig.set("USB2", "guncon2_numdevice", "0")

    # gun crosshairs
    if pcsx2_iniconfig.has_section("USB1"):
        if system.config.get("pcsx2_crosshairs") == "1":
            pcsx2_iniconfig.set("USB1", "guncon2_cursor_path", str(_PCSX2_CFGDIR / "crosshairs" / "default.png"))
            pcsx2_iniconfig.set("USB1", "guncon2_cursor_color", "#0000ff")  # blue
        else:
            pcsx2_iniconfig.set("USB1", "guncon2_cursor_path", "")
    if pcsx2_iniconfig.has_section("USB2"):
        if system.config.get("pcsx2_crosshairs") == "1":
            pcsx2_iniconfig.set("USB2", "guncon2_cursor_path", str(_PCSX2_CFGDIR / "crosshairs" / "default.png"))
            pcsx2_iniconfig.set("USB2", "guncon2_cursor_color", "#ff0000")  # red
        else:
            pcsx2_iniconfig.set("USB2", "guncon2_cursor_path", "")

    # hack for the fog bug for guns (Time Crisis - Crisis Zone)
    fog_files = [
        _PCSX2_CFGDIR / "textures" / "SCES-52530" / "replacements" / "c321d53987f3986d-eadd4df7c9d76527-00005dd4.png",
        _PCSX2_CFGDIR / "textures" / "SLUS-20927" / "replacements" / "c321d53987f3986d-eadd4df7c9d76527-00005dd4.png",
    ]
    if system.config.get("pcsx2_crisis_fog") == "true":
        for file_path in fog_files:
            texture_directory_path = _PCSX2_TEXTURES / file_path.parent.parent.name / "replacements"
            texture_directory_path.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file_path, texture_directory_path / file_path.name)
        # texture replacements must be enabled for the fog fix to take effect
        pcsx2_iniconfig.set("EmuCore/GS", "LoadTextureReplacements", "true")
    else:
        for file_path in fog_files:
            texture_directory_path = _PCSX2_TEXTURES / file_path.parent.parent.name / "replacements"
            target_file_path = texture_directory_path / file_path.name
            if target_file_path.is_file():
                target_file_path.unlink()

    ## [Input]
    pcsx2_iniconfig = _pcsx2_gen_controllers_config(
        pcsx2_iniconfig, system, controllers, metadata, guns, wheels, playingWithWheel)

    ## [GameList]
    if not pcsx2_iniconfig.has_section("GameList"):
        pcsx2_iniconfig.add_section("GameList")

    pcsx2_iniconfig.set("GameList", "RecursivePaths", str(ROMS / "ps2"))

    with PCSX2_CFG.open('w') as configfile:
        pcsx2_iniconfig.write(configfile)


def getInGameRatio(self, config, gameResolution, rom):
    config_ratio = getGfxRatioFromConfig(config, gameResolution)
    if config_ratio == "16:9" or (config_ratio == "Stretch" and gameResolution["width"] / float(gameResolution["height"]) > ((16.0 / 9.0) - 0.1)):
        return 16/9
    return 4/3