from __future__ import annotations

import itertools
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.launcher.configgen import Command
from runtime.launcher.configgen.Emulator import generate_bash_wrapper
from runtime.launcher.configgen.controller import generate_sdl_game_controller_config
from runtime.launcher.configgen.exceptions import MissingCore, RetroboxException
from runtime.launcher.configgen.generators.Generator import Generator
from runtime.launcher.configgen.generators.libretro import (
    libretroRetroarchCustom
)
from runtime.launcher.configgen.generators.libretro.libretroPaths import (
    _RETROARCH_BIN,
    _RETROARCH_CONFIG,
    _RETROARCH_XDG,
    RETROARCH_CORES,
    RETROARCH_CUSTOM,
    RETROARCH_SHADERS,
    RETROARCH_SHARE
)
from runtime.retrobox_paths import (
    _UTILS_DIR,
    BIOS,
    CMDFILES_DIR,
    OVERLAYS,
    ROMS,
    SAVES,
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
    def _core_filename(self, core: str) -> str:
        """Traduce nombres alias de Batocera a nombres de fichero upstream de RetroArch."""
        _MAP = {
            'pce':                    'mednafen_pce',
            'pce_fast':               'mednafen_pce_fast',
            'vb':                     'mednafen_vb',
            'genesisplusgx':          'genesis_plus_gx',
            'genesisplusgx-expanded': 'genesis_plus_gx',
            'genesisplusgx-wide':     'genesis_plus_gx_wide',
            'snes9x_next':            'snes9x2010',
            'flycastvl':              'flycast',
            'bsnes_hd':               'bsnes_hd_beta',
            'mupen64plus-next':       'mupen64plus_next',
            'beetle-saturn':          'mednafen_saturn',
            'mesens':                 'mesen-s',
        }
        return _MAP.get(core, core)
    
    def supportsInternalBezels(self):
        return True
    
    def usesOpenGLDirectPreload(self, config) -> bool:
        return config.get("gfxbackend") == "glcore" \
        or config.get("gfxbackend") == "gl"

    def getHotkeysContext(self) -> HotkeysContext:
        # f12 for coin : set in libretroMameConfig.py, others in libretroControllers.py
        return {
            "name": "retroarch",
            "keys": { "exit": ["KEY_LEFTSHIFT", "KEY_ESC"], "menu": ["KEY_LEFTSHIFT", "KEY_F1"], "pause": ["KEY_LEFTSHIFT", "KEY_P"], "coin": "KEY_F12",
                      "save_state": ["KEY_LEFTSHIFT", "KEY_F3"], "restore_state": ["KEY_LEFTSHIFT", "KEY_F4"], "previous_slot": ["KEY_LEFTSHIFT", "KEY_F6"], "next_slot": ["KEY_LEFTSHIFT", "KEY_F5"],
                      "rewind": ["KEY_LEFTSHIFT", "KEY_F11"], "fastforward": ["KEY_LEFTSHIFT", "KEY_F12"], "reset": ["KEY_LEFTSHIFT", "KEY_F10"], "translation": ["KEY_LEFTSHIFT", "KEY_F9"]
                     }
        }

    # Main entry of the module
    # Configure retroarch and return a command
    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        # Fix for the removed MESS/MAMEVirtual cores
        if system.config.core in [ 'mess', 'mamevirtual' ]:
            system.config['core'] = 'mame'

        # Get the graphics backend first
        gfx_backend = gfx_backend_get(system)

        # Get the shader before writing the config, we may need to disable bezels based on the shader.
        render_config = system.renderconfig
        alt_decoration = videoMode.get_alt_decoration(system.name, rom, 'retroarch')
        game_shader = None
        shader_bezel = False
        video_shader: Path | None = None
        if alt_decoration == "0":
            if 'shader' in render_config:
                game_shader = render_config['shader']
        else:
            if 'shader-' + str(alt_decoration) in render_config:
                game_shader = render_config['shader-' + str(alt_decoration)]
            elif 'shader' in render_config:
                game_shader = render_config['shader']

        if 'shader' in render_config and game_shader is not None:
            if (gfx_backend == 'glcore' or gfx_backend == 'vulkan') \
            or (system.config.core in libretroConfig.coreForceSlangShaders):
                shader_type = "slang"
            else:
                shader_type = "glsl"

            shader_filename = f"{game_shader}.{shader_type}p"
            _logger.debug("searching shader %s", shader_filename)
            if (_SHADERS_DIR / shader_filename).exists():
                video_shader_dir = _SHADERS_DIR
                _logger.debug("shader %s found in %s", shader_filename, _SHADERS_DIR)
            else:
                video_shader_dir = RETROARCH_SHADERS / f"shaders_{shader_type}"
            video_shader = video_shader_dir / shader_filename

            # If the shader filename contains noBezel, activate Shader Bezel mode.
            if "noBezel" in video_shader.name:
                shader_bezel = True

        # Settings batocera default config file if no user defined one
        if 'configfile' not in system.config:
            # Using batocera config file
            system.config['configfile'] = str(RETROARCH_CUSTOM)
            # Create retroarchcustom.cfg if does not exists
            if not RETROARCH_CUSTOM.is_file():
                libretroRetroarchCustom.generate_retroarch_custom()
            #  Write controllers configuration files
            retroconfig = UnixSettings(RETROARCH_CUSTOM, separator=' ')

            if 'lightgun_map' in system.config:
                lightgun = system.config.get_bool('lightgun_map')
            else:
                # Lightgun button mapping breaks lr-mame's inputs, disable if left on auto
                lightgun = system.config.core not in [ 'mess', 'mamevirtual', 'same_cdi', 'mame078plus' ]
            libretroControllers.writeControllersConfig(retroconfig, system, playersControllers, lightgun)
            # force pathes
            libretroRetroarchCustom.generate_rarch_custom_paths(retroconfig)
            # Write configuration to retroarchcustom.cfg
            bezel = system.config.get('bezel') or None
            # some systems (ie gw) won't bezels
            if system.config.get_bool('forceNoBezel'):
                bezel = None

            libretroConfig.writeLibretroConfig(self, retroconfig, system, playersControllers, metadata, guns, wheels, rom, bezel, shader_bezel, gameResolution, gfx_backend)
            retroconfig.write()

            # duplicate config to mapping files while ra now split in 2 parts
            remapconfigDir = _RETROARCH_CONFIG / "config" / "remaps" / "common"
            mkdir_if_not_exists(remapconfigDir)
            #shutil.copyfile(RETROARCH_CUSTOM, remapconfigDir / "common.rmp")
        # Batocera usa nombres alias; los ficheros upstream de RetroArch usan nombres distintos

        libretro_core = RETROARCH_CORES / f"{self._core_filename(system.config.core)}_libretro.so"
        info_file = RETROARCH_SHARE / f"{self._core_filename(system.config.core)}_libretro.info"
        # Retroarch core on the filesystem
        #_logger.warning("DEBUG core seleccionado: %r", system.config.core)

        # for each core, a file /usr/lib/<core>.info must exit, otherwise, info such as rewinding/netplay will not work
        # to do a global check : cd /usr/lib/libretro && for i in *.so; do INF=$(echo $i | sed -e s+/usr/lib/libretro+/usr/share/libretro/info+ -e s+\.so+.info+); test -e "$INF" || echo $i; done
        _logger.debug("Looking for core info: %s", info_file)   # ← añade esto
        if not info_file.exists() and not configure_emulator(rom):
            _logger.error("Core not found: %s", system.config.core)
            raise MissingCore

        # The command to run
        dont_append_rom = False
        # For the NeoGeo CD (lr-fbneo) it is necessary to add the parameter: --subsystem neocd
        if system.name == 'neogeocd' and system.config.core == "fbneo":
            args_array = ["-L", libretro_core, "--subsystem", "neocd", "--config", system.config['configfile']]
        # Set up GB/GBC Link games to use 2 different ROMs if needed
        if system.name == 'gb2players' or system.name == 'gbc2players':
            GBMultiROM: list[Path] = []
            GBMultiSys: list[str] = []
            # If ROM file is a .gb2 text, retrieve the filenames
            if rom.suffix.lower() in ['.gb2', '.gbc2']:
                with rom.open() as fp:
                    for line in fp:
                        GBMultiText = line.strip()
                        if GBMultiText.lower().startswith("gb:"):
                            GBMultiROM.append(ROMS / "gb" / GBMultiText[3:])
                            GBMultiSys.append("gb")
                        elif GBMultiText.lower().startswith("gbc:"):
                            GBMultiROM.append(ROMS / "gbc" / GBMultiText[4:])
                            GBMultiSys.append("gbc")
                        else:
                            GBMultiROM.append(ROMS / system.name / GBMultiText)
                            if system.name == "gb2players":
                                GBMultiSys.append("gb")
                            else:
                                GBMultiSys.append("gbc")
            else:
                # Otherwise fill in the list with the single game
                GBMultiROM.append(rom)
                if system.name == "gb2players":
                    GBMultiSys.append("gb")
                else:
                    GBMultiSys.append("gbc")
            # If there are at least 2 games in the list, use the alternate command line
            if len(GBMultiROM) >= 2:
                args_array = ["-L", libretro_core, GBMultiROM[0], "--subsystem", "gb_link_2p", GBMultiROM[1], "--config", system.config['configfile']]
                dont_append_rom = True
            else:
                args_array = ["-L", libretro_core, "--config", system.config['configfile']]
            # Handling for the save copy
            if system.config.get('sync_saves') == '1':
                if len(GBMultiROM) >= 2:
                    GBMultiSave = [GBMultiROM[0].stem + ".srm", GBMultiROM[1].stem + ".srm"]
                else:
                    GBMultiSave = [GBMultiROM[0].stem + ".srm"]
                # Verifies all the save paths exist
                # Prevents copy errors if they don't
                mkdir_if_not_exists(SAVES / "gb")
                mkdir_if_not_exists(SAVES / "gbc")
                mkdir_if_not_exists(SAVES / "gb2players")
                mkdir_if_not_exists(SAVES / "gbc2players")
                # Copies the saves if they exist
                for x in range(len(GBMultiSave)):
                    saveFile = SAVES / GBMultiSys[x] / GBMultiSave[x]
                    newSaveFile = SAVES / system.name / GBMultiSave[x]
                    if saveFile.exists():
                        shutil.copy(saveFile, newSaveFile)
                # Generates a script to copy the saves back on exit
                # Starts by making sure script paths exist
                mkdir_if_not_exists(_UTILS_DIR / "gb2savesync")
                script_file = _UTILS_DIR / "gb2savesync" / "exitsync.sh"
                if script_file.exists():
                    script_file.unlink()
                GBMultiScript = script_file.open("w")
                GBMultiScript.write("#!/bin/bash\n")
                GBMultiScript.write("#This script is created by the Game Boy link cable system to sync save files.\n")
                GBMultiScript.write("#\n")
                GBMultiScript.write("\n")
                GBMultiScript.write("case $1 in\n")
                GBMultiScript.write("   gameStop)\n")
                # The only event is gameStop, checks to make sure it was called by the right system
                GBMultiScript.write("       if [ $2 = 'gb2players' ] || [ $2 = 'gbc2players' ]\n")
                GBMultiScript.write("       then\n")
                for x in range(len(GBMultiSave)):
                    saveFile = f"{SAVES}/" + GBMultiSys[x] + "/" + GBMultiSave[x]
                    newSaveFile = f"{SAVES}/" + system.name + "/" + GBMultiSave[x]
                    GBMultiScript.write('           cp "' + newSaveFile + '" "' + saveFile + '"\n')
                GBMultiScript.write("       fi\n")
                # Deletes itself after running
                GBMultiScript.write(f"       rm {script_file}\n")
                GBMultiScript.write("   ;;\n")
                GBMultiScript.write("esac\n")
                GBMultiScript.close()
                # Make it executable
                script_file.chmod(script_file.stat().st_mode | 0o111)
        # PURE zip games uses the same commandarray of all cores. .pc and .rom  uses owns
        elif system.name == 'dos':
            if rom.suffix == '.dos' or rom.suffix == '.pc':
                if (rom / f"{rom.stem}.bat").exists() and " " not in rom.stem:
                    exe = rom / f"{rom.stem}.bat"
                elif (rom / "dosbox.bat").exists() and not (rom / f"{rom.stem}.bat").exists():
                    exe = rom / "dosbox.bat"
                else:
                    exe = rom
                args_array = ["-L", libretro_core, "--config", system.config['configfile'], exe]
                dont_append_rom = True
            else:
                args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        # Pico-8 multi-carts (might work only with official Lexaloffe engine right now)
        elif system.name == 'pico8':
            if rom.suffix.lower() == ".m3u":
                with rom.open("r") as fpin:
                    lines = fpin.readlines()
                rom = rom.absolute().parent / lines[0].strip()
            args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        # tyrquake - set directory
        elif system.name == 'quake':
            if "scourge" in rom.name.lower():
                rom = Path(f'{ROMS}/quake/hipnotic/pak0.pak')
            elif "dissolution" in rom.name.lower():
                rom = Path(f'{ROMS}/quake/rogue/pak0.pak')
            else:
                rom = Path(f'{ROMS}/quake/id1/pak0.pak')
            args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        # vitaquake2 - choose core based on directory
        elif system.name == 'quake2':
            if "reckoning" in rom.name.lower():
                system.config['core'] = "vitaquake2-xatrix"
                rom = Path(f'{ROMS}/quake2/xatrix/pak0.pak')
            elif "zero" in rom.name.lower():
                system.config['core'] = "vitaquake2-rogue"
                rom = Path(f'{ROMS}/quake2/rogue/pak0.pak')
            elif "zaero" in rom.name.lower():
                system.config['core'] = "vitaquake2-zaero"
                rom = Path(f'{ROMS}/quake2/zaero/pak0.pak')
            else:
                rom = Path(f'{ROMS}/quake2/baseq2/pak0.pak')
            # set the updated core name
            libretro_core = RETROARCH_CORES / f"{system.config.core}_libretro.so"
            args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        # doom3
        elif system.name == 'doom3':
            with rom.open('r') as file:
                first_line = file.readline().strip()
            # creating the new 'rom_path' variable by combining the directory path and the first line
            rom = rom.parent / first_line
            _logger.debug("New rom path: %s", rom)
            # choose core based on new rom directory
            directory_parts = rom.parent.parts
            if "d3xp" in directory_parts:
                system.config['core'] = "boom3_xp"
            libretro_core = RETROARCH_CORES / f"{system.config.core}_libretro.so"
            args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        # super mario wars - verify assets from Content Downloader
        elif system.name == 'superbroswar':
            romdir = rom.absolute().parent
            assetdirs = [
                "music/world/Standard", "music/game/Standard/Special", "music/game/Standard/Menu", "filters", "worlds/KingdomHigh",
                "worlds/MrIsland", "worlds/Sky World", "worlds/Smb3", "worlds/Simple", "worlds/screenshots", "worlds/Flurry World",
                "worlds/MixedRiver", "worlds/Contest", "gfx/skins", "gfx/packs/Retro/fonts", "gfx/packs/Retro/modeobjects",
                "gfx/packs/Retro/eyecandy", "gfx/packs/Retro/awards", "gfx/packs/Retro/powerups", "gfx/packs/Retro/menu",
                "gfx/packs/Classic/projectiles", "gfx/packs/Classic/fonts", "gfx/packs/Classic/modeobjects", "gfx/packs/Classic/world",
                "gfx/packs/Classic/world/thumbnail", "gfx/packs/Classic/world/preview", "gfx/packs/Classic/modeskins",
                "gfx/packs/Classic/hazards", "gfx/packs/Classic/blocks", "gfx/packs/Classic/backgrounds", "gfx/packs/Classic/tilesets/SMB2",
                "gfx/packs/Classic/tilesets/Expanded", "gfx/packs/Classic/tilesets/SMB1", "gfx/packs/Classic/tilesets/Classic",
                "gfx/packs/Classic/tilesets/SMB3", "gfx/packs/Classic/tilesets/SuperMarioWorld", "gfx/packs/Classic/tilesets/YoshisIsland",
                "gfx/packs/Classic/eyecandy", "gfx/packs/Classic/awards", "gfx/packs/Classic/powerups", "gfx/packs/Classic/menu",
                "gfx/leveleditor", "gfx/docs", "sfx/packs/Classic", "sfx/announcer/Mario",
                "maps/tour", "maps/cache", "maps/screenshots", "maps/special", "tours",
            ]
            try:
                for assetdir in assetdirs:
                    os.chdir(romdir / assetdir)
                os.chdir(romdir)
            except FileNotFoundError as e:
                _logger.error("ERROR: Game assets not installed. You can get them from the Batocera Content Downloader.")
                raise RetroboxException("Game assets not installed. You can get them from the Batocera Content Downloader.") from e

            args_array = ["-L", libretro_core, "--config", system.config['configfile']]
        else:
            # lógica para abrir retroarch sin rom desde el menú de config de emuladores
            if configure_emulator(rom):
                dont_append_rom = True
                args_array = ["--config", system.config['configfile']]
            else:
                # caso general para la mayoría de emuladores y cores
                args_array = ["-L", libretro_core, "--config", system.config['configfile']]

        configToAppend: list[Path] = []

        # Custom configs - per core
        custom_cfg = _RETROARCH_CONFIG / f"{system.name}.cfg"
        if custom_cfg.is_file():
            configToAppend.append(custom_cfg)

        # Custom configs - per game
        custom_game_cfg = _RETROARCH_CONFIG / system.name / f"{rom.name}.cfg"
        if custom_game_cfg.is_file():
            configToAppend.append(custom_game_cfg)

        # Overlay management
        overlay_file = OVERLAYS / system.name / f"{rom.name}.cfg"
        if overlay_file.is_file():
            configToAppend.append(overlay_file)

        # RetroArch 1.7.8 (Batocera 5.24) now requires the shaders to be passed as command line argument
        if video_shader is not None:
            args_array.extend(["--set-shader", video_shader])

        # Generate the append
        if configToAppend:
            args_array.extend(["--appendconfig", "|".join(str(config) for config in configToAppend)])

        # Netplay mode
        if netplay_mode := system.config.get('netplay.mode'):
            if netplay_mode == 'host':
                args_array.append("--host")
            elif netplay_mode == 'client' or netplay_mode == 'spectator':
                args_array.extend(["--connect", system.config['netplay.server.ip']])
            if 'netplay.server.port' in system.config:
                args_array.extend(["--port", system.config['netplay.server.port']])
            if 'netplay.server.session' in system.config:
                args_array.extend(["--mitm-session", system.config['netplay.server.session']])
            if 'netplay.nickname' in system.config:
                args_array.extend(["--nick", system.config['netplay.nickname']])

        # Verbose logs
        args_array.extend(['--verbose'])

        if system.name == 'snes-msu1' or system.name == 'satellaview':
            if "squashfs" in str(rom) and rom.is_dir():
                rom = next(itertools.chain(rom.glob('*.sfc'), rom.glob('*.smc')))
        elif system.name == 'sgb-msu1':
            if "squashfs" in str(rom) and rom.is_dir():
                rom = next(itertools.chain(rom.glob('*.gb'), rom.glob('*.gbc')))
        elif system.name == 'megadrive-msu':  # noqa: SIM102
            if "squashfs" in str(rom) and rom.is_dir():
                rom = next(rom.glob('*.md'))

        if system.name == 'scummvm':
            rom = rom.parent / rom.name
            if rom.stat().st_size == 0:
                # File is empty, run game directly
                rom = rom.with_suffix('')

        if system.name == 'reminiscence':
            with rom.open() as file:
                first_line = file.readline().strip()
            rom = rom.parent / first_line

        # Use command line instead of ROM file for MAME variants
        if system.config.core in [ 'mame', 'mess', 'mamevirtual', 'same_cdi' ]:
            dont_append_rom = True
            args_array.append(f"{CMDFILES_DIR}/{rom.stem}.cmd")

        if system.config.core == 'hatarib':
            biosdir = BIOS / "hatarib"
            if not biosdir.exists():
                biosdir.mkdir()
            targetlink = biosdir / "hdd"
            #retroarch can't use hdd files outside his system directory (/userdata/bios)
            if targetlink.exists():
                targetlink.unlink()
            if rom.suffix.lower() in ['.hd', '.gemdos']:
                #don't pass hd drive as parameter, it need to be added in configuration
                dont_append_rom = True
                targetlink.unlink(missing_ok=True)
                targetlink.symlink_to(rom)

        if not dont_append_rom:
            args_array.append(rom)

        if (state_slot := system.config.get_str('state_slot')) and not system.config.get('state_filename', '.auto').endswith(".auto"):
            # if the file ends by .auto, this is the auto loading, else it is the states
            # retroarch need the file be named with .entry at the end to load the state
            # a link would work, but on fat32, we need to copy
            args_array.extend(["-e", state_slot])

        # force X11/Xwayland if we are using MangoHud with OpenGL backend (causes crashes in my PC)
        use_hud = bool(
            (hud_value := system.config.get('hud')) and hud_value.lower() != 'none'
        )
        
        forced_x11 = \
            system.config.get_bool("force_x11", False, return_values=(True, False))
        
        if use_hud and self.usesOpenGLDirectPreload:
            forced_x11 = True

        # generate bash wrapper
        command_wrapper = [generate_bash_wrapper(
            system.config.emulator, _RETROARCH_BIN, args_array,
            force_x11=forced_x11
        )]

        return Command.Command(array=command_wrapper, env={
            "XDG_CONFIG_HOME": _RETROARCH_XDG,
            "SDL_GAMECONTROLLERCONFIG": generate_sdl_game_controller_config(playersControllers),
            #"KWIN_DRM_NO_AMS": "1",
            #"PULSE_LATENCY_MSEC": "60"
        })

def _gfx_backend_check(backend: str):
    if backend == "vulkan" \
    and vulkan.is_available():
        return "vulkan"

    if backend == "glcore" \
    and videoMode.getGLVendor() in ["nvidia", "amd"] \
    and videoMode.getGLVersion() >= 3.1:
        return "glcore"

    return "gl"

def gfx_backend_get(system: Emulator) -> str:
    backend = system.config.get("gfxbackend")

    if backend:
        set_manually = True
        backend = _gfx_backend_check(backend)
    else:
        set_manually = False
        backend = _gfx_backend_check("glcore")

    # Retroarch has flipped between using opengl or gl, correct the setting here if needed.
    if backend == "opengl":
        backend = "gl"

    # No tocar si el usuario lo eligió manualmente
    if not set_manually:
        core = system.config.core

        # Overrides específicos por core
        if backend in ["gl", "glcore"]:
            if backend == "gl" \
            and core in ['kronos', 'mupen64plus-next', 'melonds', 'beetle-psx-hw']:
                backend = "glcore"
            if backend == "glcore" and core in ['parallel_n64', 'yabasanshiro', 'boom3']:
                backend = "gl"

    return backend
