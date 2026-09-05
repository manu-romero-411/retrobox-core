from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

from configgen.generators.libretro.libretroControllers import clearGunInputsForPlayer, configureGunInputsForPlayer

from ... import controllersConfig
from runtime.paths import (
    BIOS, CHEATS, ES_GAMES_METADATA, RECORDINGS,
    SAVES, SCREENSHOTS, SHADER_BEZELS_DIR, mkdir_if_not_exists
)
from ...controller import Controller
from ...settings.unixSettings import UnixSettings
from ...utils import bezels as bezelsUtil
from ...utils import metadata as metadataUtils

from .libretroPaths import (
    _RETROARCH_CFGDIR,
    _RETROARCH_SHARE,
    RETROARCH_ASSETS,
    RETROARCH_CORE_CUSTOM,
    RETROARCH_CORES,
    RETROARCH_OVERLAY_CONFIG,
    RETROARCH_SHADERS
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from ...controller import Controllers
    from ...Emulator import Emulator
    from ..Generator import Generator
    from ...gun import Gun, Guns
    from ...batoceraTypes import DeviceInfoMapping, Resolution

_logger = logging.getLogger(__name__)


class _GunMappingItem(TypedDict):
    device: NotRequired[int]
    p1: NotRequired[int]
    p2: NotRequired[int]
    p3: NotRequired[int]
    p4: NotRequired[int]
    gameDependant: NotRequired[list[dict[str, Any]]]


ratioIndexes = ["4/3", "16/9", "16/10", "16/15", "21/9", "1/1", "2/1", "3/2", "3/4", "4/1", "9/16", "5/4", "6/5", "7/9", "8/3",
                "8/7", "19/12", "19/14", "30/17", "32/9", "config", "squarepixel", "core", "custom", "full"]

coreToP1Device = {'atari800': '513', 'cap32': '513', '81': '259', 'fuse': '769'}
coreToP2Device = {'atari800': '513', 'fuse': '513'}

systemNoRewind = {'sega32x', 'psx', 'zxspectrum', 'n64', 'dreamcast', 'atomiswave', 'naomi', 'saturn', 'dice', 'pd777'}

# Mapeo de dispositivo de pistola por core/sistema. OJO: los bloques
# "gameDependant" se consultan (nunca se mutan) al copiar sobre un dict
# nuevo en createLibretroConfig — ver el comentario junto a su uso.
GUN_CORE_MAPPING: dict[str, dict[str, _GunMappingItem]] = {
    "bsnes": {"default": {"device": 260, "p2": 0, "gameDependant": [
        {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "516"},
        {"key": "reversedbuttons", "value": "true", "mapcorekey": "bsnes_touchscreen_lightgun_superscope_reverse", "mapcorevalue": "ON"},
    ]}},
    "snes9x": {"default": {"device": 260, "p2": 0, "p3": 1, "gameDependant": [
        {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "516"},
        {"key": "type", "value": "justifier", "mapkey": "device_p3", "mapvalue": "772"},
        {"key": "type", "value": "macsrifle", "mapkey": "device", "mapvalue": "1028"},
        {"key": "reversedbuttons", "value": "true", "mapcorekey": "snes9x_superscope_reverse_buttons", "mapcorevalue": "enabled"},
    ]}},
    "fceumm": {"default": {"device": 258, "p2": 0}},
    "genesis_plus_gx": {
        "megadrive": {"device": 516, "p2": 0, "gameDependant": [
            {"key": "type", "value": "justifier", "mapkey": "device", "mapvalue": "772"},
        ]},
        "mastersystem": {"device": 260, "p1": 0, "p2": 1},
    },
    "flycast": {"default": {"device": 4, "p1": 0, "p2": 1, "p3": 2, "p4": 3}},
    "dolphin": {"default": {"device": 769, "p1": 0, "p2": 1, "p3": 2, "p4": 3}},
}

# Ajustes fijos de retroarch.cfg que no dependen de system.config. Se
# reescriben en CADA lanzamiento (como parte del mismo dict que aplica
# createLibretroConfig), así que ganan siempre sobre cualquier cambio hecho
# por el usuario desde el menú de RetroArch en la sesión anterior — no hay
# "solo la primera vez" ni fichero aparte con --appendconfig.
#
# Trade-off deliberado: el usuario YA NO puede cambiar estas claves en
# concreto desde el menú de RetroArch y que el cambio persista (p.ej. subir
# audio_volume o tocar confirm_close se revertirá en el siguiente
# lanzamiento). Si alguna necesita ser tocable libremente, sácala de aquí.
_FIXED_RETROARCH_SETTINGS: dict[str, str] = {
    'menu_driver': '"ozone"',
    'menu_show_load_content_animation': '"false"',
    'content_show_favorites': '"false"',
    'content_show_images': '"false"',
    'content_show_music': '"false"',
    'content_show_video': '"false"',
    'content_show_history': '"false"',
    'content_show_playlists': '"false"',
    'content_show_add': '"false"',
    'menu_show_load_core': '"false"',
    'menu_show_load_content': '"false"',
    'menu_show_online_updater': '"true"',
    'menu_show_core_updater': '"true"',
    'video_aspect_ratio_auto': '"false"',
    'video_gpu_screenshot': '"true"',
    'video_shader_enable': '"false"',
    'aspect_ratio_index': '"22"',
    'audio_volume': '"2.0"',
    'global_core_options': '"true"',
    'config_save_on_exit': '"true"',
    'savestate_auto_save': '"false"',
    'savestate_auto_load': '"false"',
    'menu_swap_ok_cancel_buttons': '"true"',
    'rgui_extended_ascii': '"true"',
    'rgui_show_start_screen': '"false"',
    'video_font_enable': '"true"',
    'savestate_thumbnail_enable': '"true"',
    'all_users_control_menu': '"false"',
    'cheevos_badges_enable': '"true"',
    'builtin_imageviewer_enable': '"false"',
    'fps_update_interval': '"30"',
    'confirm_close': '"false"',
    'confirm_quit': '"false"',
    'video_fullscreen': '"true"',
    'video_windowed_fullscreen': "'true'",
    'sort_savefiles_by_content_enable': '"true"',
    'sort_savestates_by_content_enable': '"true"'
}


def open_unix_settings(path: Path, /) -> UnixSettings:
    """Abre (o recrea si está corrupto) un UnixSettings, creando su directorio padre.
    Público: también lo usa LibretroGenerator.generate() para abrir retroarch.cfg."""
    mkdir_if_not_exists(path.parent)
    try:
        return UnixSettings(path, separator=' ')
    except UnicodeError:
        path.unlink()
        return UnixSettings(path, separator=' ')


def rarch_custom_paths(system: Emulator) -> dict[str, str]:
    """Rutas fijas de retroarch.cfg. Función pura: quien la llama decide
    dónde y cuándo aplicarla (ver LibretroGenerator.generate)."""
    
    mkdir_if_not_exists(BIOS / system.name)
    mkdir_if_not_exists(SAVES / system.name)
    
    return {
        'core_options_path': f'"{_RETROARCH_CFGDIR}/cores/retroarch-core-options.cfg"',
        'assets_directory': f'"{RETROARCH_ASSETS}"',
        'screenshot_directory': f'"{SCREENSHOTS}/"',
        'recording_output_directory': f'"{RECORDINGS}/"',
        'extraction_directory': f'"{_RETROARCH_SHARE}/extractions/"',
        'cheat_database_path': f'"{CHEATS}/cht/"',
        'cheat_settings_path': f'"{CHEATS}/saves/"',
        'system_directory': f'"{BIOS}/"',
        'joypad_autoconfig_dir': f'"{_RETROARCH_CFGDIR}/autoconfig/"',
        'video_shader_dir': f'"{RETROARCH_SHADERS}/"',
        'video_font_path': '"/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf"',
        'video_filter_dir': f'"{_RETROARCH_SHARE}/filters/video"',
        'audio_filter_dir': f'"{_RETROARCH_SHARE}/filters/audio"',
    }


def writeLibretroConfig(
    generator: Generator, retroconfig: UnixSettings, system: Emulator, controllers: Controllers,
    metadata: Mapping[str, str], guns: Guns, wheels: DeviceInfoMapping, rom: Path, bezel: str | None,
    shaderBezel: bool, gameResolution: Resolution, gfxBackend: str, /,
) -> None:
    writeLibretroConfigToFile(retroconfig, createLibretroConfig(generator, system, controllers, metadata, guns, wheels, rom, bezel, shaderBezel, gameResolution, gfxBackend))


def createLibretroConfig(
    generator: Generator, system: Emulator, controllers: Controllers, metadata: Mapping[str, str],
    guns: Guns, wheels: DeviceInfoMapping, rom: Path, bezel: str | None, shaderBezel: bool,
    gameResolution: Resolution, gfxBackend: str, /,
) -> dict[str, object]:

    core_settings = open_unix_settings(RETROARCH_CORE_CUSTOM)

    # Arranca con los ajustes fijos (ver _FIXED_RETROARCH_SETTINGS): se
    # reescriben en cada lanzamiento y ganan sobre cualquier cambio hecho
    # desde el menú de RetroArch en la sesión anterior. Todo lo que sigue
    # puede sobreescribir claves concretas de este dict según el sistema/core.
    retroarch_config: dict[str, object] = dict(_FIXED_RETROARCH_SETTINGS)
    render_config = system.renderconfig
    system_core = system.config.core

    retroarch_config['video_driver'] = f'"{gfxBackend}"'
    retroarch_config['pause_nonactive'] = 'true'
    mkdir_if_not_exists(_RETROARCH_CFGDIR / 'cache')
    retroarch_config['cache_directory'] = _RETROARCH_CFGDIR / 'cache'
    retroarch_config['libretro_directory'] = RETROARCH_CORES
    retroarch_config['libretro_info_path'] = RETROARCH_CORES
    retroarch_config['builtin_imageviewer_enable'] = 'false'
    retroarch_config['assets_directory'] = str(RETROARCH_ASSETS)

    # Directorio de guardado por sistema
    retroarch_config['sort_savefiles_enable'] = 'false'
    retroarch_config['sort_savestates_enable'] = 'false'
    retroarch_config['savestate_directory'] = Path(f"{SAVES}")
    retroarch_config['savefile_directory'] = Path(f"{SAVES}")

    if system.config.core == 'tgbdual':
        retroarch_config['aspect_ratio_index'] = str(ratioIndexes.index("core"))

    language = system.config.get_str('retroarch.user_language', system.config.get_str('system.language'))
    if language in ('1', 'ja_JP'):
        retroarch_config['video_font_path'] = "/usr/share/fonts/truetype/noto/NotoSansJP-VF.ttf"
    elif language in ('10', 'ko_KR'):
        retroarch_config['video_font_path'] = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    elif language in ('11', 'zh_TW'):
        retroarch_config['video_font_path'] = "/usr/share/fonts/truetype/noto/NotoSansTC-VF.ttf"
    elif language in ('12', 'zh_CN'):
        retroarch_config['video_font_path'] = "/usr/share/fonts/truetype/noto/NotoSansSC-VF.ttf"

    retroarch_config['load_dummy_on_core_shutdown'] = '"false"'

    # INPUT
    retroarch_config['input_joypad_driver'] = 'udev'
    retroarch_config['input_driver'] = 'udev'
    retroarch_config['input_max_users'] = str(max(len(controllers), 1))
    retroarch_config['input_libretro_device_p1'] = '1'
    retroarch_config['input_libretro_device_p2'] = '1'

    if system.config.core in ('puae', 'puae2021', 'vice_x64'):
        retroarch_config['input_player1_analog_dpad_mode'] = '3'
        retroarch_config['input_player2_analog_dpad_mode'] = '3'

    if system.config.core in coreToP1Device:
        retroarch_config['input_libretro_device_p1'] = coreToP1Device[system.config.core]
    if system.config.core in coreToP2Device:
        retroarch_config['input_libretro_device_p2'] = coreToP2Device[system.config.core]

    if system.config.core in ('snes9x', 'snes9x_next'):
        retroarch_config['input_libretro_device_p1'] = system.config.get(f'controller1_{system.config.core}', '1')
        retroarch_config['input_libretro_device_p2'] = system.config.get(f'controller2_{system.config.core}', '257' if len(controllers) > 2 else '1')
        retroarch_config['input_libretro_device_p3'] = system.config.get('controller3_snes9x', '1')

    if system.config.core == 'fceumm':
        retroarch_config['input_libretro_device_p1'] = system.config.get('controller1_nes', '1')
        retroarch_config['input_libretro_device_p2'] = system.config.get('controller2_nes', '1')

    if system.config.core == 'mednafen_psx':
        if ctrl := system.config.get('beetle_psx_hw_Controller1'):
            retroarch_config['input_libretro_device_p1'] = ctrl
            retroarch_config['input_player1_analog_dpad_mode'] = '0' if ctrl != '1' else '1'
        if ctrl := system.config.get('beetle_psx_hw_Controller2'):
            retroarch_config['input_libretro_device_p2'] = ctrl
            retroarch_config['input_player2_analog_dpad_mode'] = '0' if ctrl != '1' else '1'

    if system.config.core == 'pcsx_rearmed':
        if ctrl := system.config.get('controller1_pcsx'):
            retroarch_config['input_libretro_device_p1'] = ctrl
            retroarch_config['input_player1_analog_dpad_mode'] = '0' if ctrl != '1' else '1'
        if ctrl := system.config.get('controller2_pcsx'):
            retroarch_config['input_libretro_device_p2'] = ctrl
            retroarch_config['input_player2_analog_dpad_mode'] = '0' if ctrl != '1' else '1'

        if system.config.use_wheels:
            deviceInfos = controllersConfig.getDevicesInformation()
            for pad in controllers:
                if pad.device_path in deviceInfos and deviceInfos[pad.device_path].get("isWheel"):
                    retroarch_config[f'input_player{pad.player_number}_analog_dpad_mode'] = '1'
                    retroarch_config[f'input_libretro_device_p{pad.player_number}'] = 773 if metadata.get("wheel_type") == "negcon" else 517

    if system.config.core == 'flycast':
        for i in range(1, 5):
            dc_val = system.config.get(f'controller{i}_dc', '1')
            if dc_val == '5':
                retroarch_config[f'input_libretro_device_p{i}'] = '1'
                retroarch_config[f'input_player{i}_analog_dpad_mode'] = '3'
            else:
                retroarch_config[f'input_libretro_device_p{i}'] = dc_val
                retroarch_config[f'input_player{i}_analog_dpad_mode'] = '0'
        if system.config.use_wheels and wheels:
            retroarch_config['input_libretro_device_p1'] = '2049'

    if system.config.core in ('genesis_plus_gx', 'genesis_plus_gx-expanded') and system.name == 'megadrive':
        retroarch_config['input_libretro_device_p1'] = system.config.get('controller1_md', '513')
        retroarch_config['input_libretro_device_p2'] = system.config.get('controller2_md', '513')

    if system.config.core in ('genesis_plus_gx', 'genesis_plus_gx-expanded', 'picodrive'):
        valid_md_guids = ["05000000c82d00005106000000010000", "03000000c82d00000650000011010000", "050000005e0400008e02000030110000", "03000000c82d00000150000011010000", "05000000c82d00000151000000010000", "0500000049190000020400001b010000"]
        valid_md_names = ["8BitDo M30 gamepad", "8Bitdo  8BitDo M30 gamepad", "8BitDo M30 Modkit", "8Bitdo  8BitDo M30 Modkit", "Retro Bit Bluetooth Controller"]
        option = 'gx' if system.config.core in ('genesis_plus_gx', 'genesis_plus_gx-expanded') else 'pd'
        for i in range(1, min(5, len(controllers) + 1)):
            pad = controllers[i - 1]
            if (pad.guid in valid_md_guids and pad.name in valid_md_names) or system.config.get(f'{option}_controller{i}_mapping', 'retropad') != 'retropad':
                for btn, val in {'btn_a': '0', 'btn_b': '1', 'btn_x': '9', 'btn_y': '10', 'btn_l': '11', 'btn_r': '8'}.items():
                    retroarch_config[f'input_player{i}_{btn}'] = val

    if system.config.core == 'genesis_plus_gx' and system.name == 'mastersystem':
        retroarch_config['input_libretro_device_p1'] = system.config.get('controller1_ms', '769')
        retroarch_config['input_libretro_device_p2'] = system.config.get('controller2_ms', '769')

    if system.config.core in ('yabasanshiro', 'beetle-saturn') and system.name == 'saturn':
        retroarch_config['input_libretro_device_p1'] = system.config.get('controller1_saturn', '1')
        retroarch_config['input_libretro_device_p2'] = system.config.get('controller2_saturn', '1')
        if system.config.core == 'beetle-saturn' and system.config.use_wheels:
            retroarch_config['input_libretro_device_p1'] = '517'

    if system.config.core in ('mupen64plus-next', 'parallel_n64'):
        valid_n64_guids = ["050000007e0500001920000001800000", "05000000c82d00006928000000010000", "030000007e0500001920000011810000", "05000000c82d00001930000001000000", "03000000c82d00001930000011010000"]
        valid_n64_names = ["N64 Controller", "Nintendo Co., Ltd. N64 Controller", "8BitDo N64 Modkit", "8BitDo 64 BT", "8BitDo 8BitDo 64 Bluetooth Controller"]
        option = 'mupen64plus' if system.config.core == 'mupen64plus-next' else 'parallel-n64'
        for i in range(1, min(5, len(controllers) + 1)):
            pad = controllers[i - 1]
            if (pad.guid in valid_n64_guids and pad.name in valid_n64_names) or system.config.get(f'{option}-controller{i}', 'retropad') != 'retropad':
                for btn, val in {'btn_a': '1', 'btn_b': '0', 'btn_x': '23', 'btn_y': '21', 'btn_l2': '22', 'btn_r2': '20', 'btn_select': '12'}.items():
                    retroarch_config[f'input_player{i}_{btn}'] = val

    # GUNS
    if system.config.use_guns:
        for g in range(len(guns)):
            clearGunInputsForPlayer(g + 1, retroarch_config)

        if system.config.core in GUN_CORE_MAPPING:
            base = GUN_CORE_MAPPING[system.config.core].get(system.name, GUN_CORE_MAPPING[system.config.core]["default"])
            # Copia superficial: no mutar GUN_CORE_MAPPING, que es compartido
            # entre lanzamientos (a nivel de módulo).
            ragunconf: dict[str, Any] = dict(base)
            raguncoreconf: dict[str, str] = {}
            if "gameDependant" in ragunconf:
                for gd in ragunconf["gameDependant"]:
                    if metadata.get(f'gun_{gd["key"]}') == gd["value"] and "mapkey" in gd and "mapvalue" in gd:
                        ragunconf[gd["mapkey"]] = gd["mapvalue"]
                    if metadata.get(f'gun_{gd["key"]}') == gd["value"] and "mapcorekey" in gd and "mapcorevalue" in gd:
                        raguncoreconf[gd["mapcorekey"]] = gd["mapcorevalue"]

            if system.config.core == "dolphin":
                raguncoreconf["dolphin_ir_offset"] = metadata.get("gun_vertical_offset", "10")
                raguncoreconf["dolphin_ir_yaw"] = metadata.get("gun_yaw", "25")
                raguncoreconf["dolphin_ir_pitch"] = metadata.get("gun_pitch", "20")

            for nplayer in range(1, 4):
                if f"p{nplayer}" in ragunconf and len(guns) - 1 >= ragunconf[f"p{nplayer}"]:
                    if f"device_p{nplayer}" in ragunconf:
                        retroarch_config[f'input_libretro_device_p{nplayer}'] = ragunconf[f"device_p{nplayer}"]
                    else:
                        retroarch_config[f'input_libretro_device_p{nplayer}'] = ragunconf.get("device", "")
                    configureGunInputsForPlayer(nplayer, guns[ragunconf[f"p{nplayer}"]], controllers, retroarch_config, system.config.core, metadata, system)

            for key in raguncoreconf:
                core_settings.save(key, f'"{raguncoreconf[key]}"')
            retroarch_config['input_overlay_show_mouse_cursor'] = "false"
    else:
        retroarch_config['input_overlay_show_mouse_cursor'] = "true"

    core_settings.write()

    # HERRAMIENTAS ESPECÍFICAS
    retroarch_config['video_smooth'] = system.config.get_bool('smooth', return_values=('true', 'false'))
    if 'shader' in render_config and render_config['shader'] not in (None, "none"):
        retroarch_config['video_shader_enable'] = 'true'
        retroarch_config['video_smooth'] = 'false'
    else:
        retroarch_config['video_shader_enable'] = 'false'

    retroarch_config['aspect_ratio_index'] = ''
    if ratio := system.config.get_str('ratio'):
        index = '22'
        if ratio in ratioIndexes:
            index = ratioIndexes.index(ratio)
        if ratio == "full":
            bezel = None
        elif system.config.get_bool(f"{system_core}-autowidescreen"):
            meta = metadataUtils.get_games_meta_data(ES_GAMES_METADATA, system.name, rom)
            if meta.get("video_widescreen") == "true":
                index = str(ratioIndexes.index("16/9"))
                bezel = None
        try:
            if '/' in ratio:
                num, den = map(float, ratio.split('/'))
                if den != 0 and (num / den) > (4/3):
                    bezel = None
        except (ValueError, TypeError):
            pass
        retroarch_config['video_aspect_ratio_auto'] = 'false'
        retroarch_config['aspect_ratio_index'] = index

    retroarch_config['rewind_enable'] = 'true' if system.name not in systemNoRewind and system.config.get_bool('rewind') else 'false'
    retroarch_config['audio_volume'] = system.config.get("audio_volume", '0')

    if system.config.get_bool('ai_service_enabled'):
        retroarch_config['ai_service_enable'] = 'true'
        retroarch_config['ai_service_mode'] = '0'
        retroarch_config['ai_service_source_lang'] = '0'
        chosen_lang = system.config.get('ai_target_lang', 'En')
        ai_url = system.config.get("ai_service_url", "http://ztranslate.net/service?api_key=BATOCERA")
        retroarch_config['ai_service_url'] = f'{ai_url}&mode=Fast&output=png&target_lang={chosen_lang}'
        retroarch_config['ai_service_pause'] = system.config.get_bool('ai_service_pause', return_values=('true', 'false'))
    else:
        retroarch_config['ai_service_enable'] = 'false'

    retroarch_config['discord_allow'] = system.config.get_bool('discordrpc', True, return_values=("true", "false"))

    # SAVESTATES Y AUTOSAVE
    autosave = system.config.get_bool('autosave', False, return_values=('true', 'false'))
    retroarch_config['savestate_auto_save'] = autosave
    retroarch_config['savestate_auto_load'] = autosave

    if system.config.get_bool('incrementalsavestates', True):
        retroarch_config['savestate_auto_index'] = 'true'
        retroarch_config['savestate_max_keep'] = '0'
    else:
        retroarch_config['savestate_auto_index'] = 'false'
        retroarch_config['savestate_max_keep'] = '50'

    retroarch_config['state_slot'] = system.config.get('state_slot', '0')

    if (state_filename := system.config.get_str('state_filename')) and state_filename.endswith('.auto'):
        retroarch_config['savestate_auto_load'] = 'true'

    try:
        writeBezelConfig(generator, bezel, shaderBezel, retroarch_config, rom, gameResolution, system, system.guns_borders_size_name(guns), system.guns_border_ratio_type(guns))
    except Exception as e:
        writeBezelConfig(generator, None, shaderBezel, retroarch_config, rom, gameResolution, system, system.guns_borders_size_name(guns), system.guns_border_ratio_type(guns))
        _logger.error("Error with bezel %s: %s", bezel, e, exc_info=True)

    retroarch_config.update(system.config.items(starts_with='retroarch.'))
    return retroarch_config




def writeLibretroConfigToFile(retroconfig: UnixSettings, config: Mapping[str, object], /) -> None:
    for setting, value in config.items():
        retroconfig.save(setting, value)


def writeBezelConfig(generator: Generator, bezel: str | None, shaderBezel: bool, retroarchConfig: dict[str, object], rom: Path, gameResolution: Resolution, system: Emulator, gunsBordersSize: str | None, gunsBordersRatio: str | None, /) -> None:
    retroarchConfig['input_overlay_hide_in_menu'] = "false"
    retroarchConfig['input_overlay_enable'] = "false"
    retroarchConfig['video_message_pos_x'] = 0.05
    retroarchConfig['video_message_pos_y'] = 0.05

    if bezel in ("none", ""):
        bezel = None

    if bezel is None and gunsBordersSize is not None:
        gunBezelFile = Path("/tmp/bezel_gun_black.png")
        gunBezelInfoFile = Path("/tmp/bezel_gun_black.info")
        w, h = gameResolution["width"], gameResolution["height"]
        innerSize, outerSize = bezelsUtil.gunBordersSize(gunsBordersSize)
        h5 = bezelsUtil.gunsBorderSize(w, h, innerSize, outerSize)
        ratio = generator.getInGameRatio(system.config, gameResolution, rom)
        top = bottom = h5
        left = right = h5
        if ratio == 4/3:
            left = right = (w - (h * 4/3)) // 2 + h5
        with gunBezelInfoFile.open("w") as fd:
            fd.write(f'{{"width":{w}, "height":{h}, "top":{top}, "left":{left}, "bottom":{bottom}, "right":{right}, "opacity":1.0, "messagex":0.22, "messagey":0.12}}')
        bezelsUtil.createTransparentBezel(gunBezelFile, w, h)
        bz_infos = {"png": gunBezelFile, "info": gunBezelInfoFile, "layout": None, "mamezip": None, "specific_to_game": True}
    else:
        if bezel is None:
            return
        bz_infos = bezelsUtil.get_bezel_infos(rom, bezel, system.name, 'retroarch')

    if bz_infos is None:
        return

    overlay_info_file: Path = cast("Path", bz_infos["info"])
    overlay_png_file: Path = cast("Path", bz_infos["png"])
    bezel_game: bool = cast("bool", bz_infos["specific_to_game"])
    infos: dict[str, Any] = {}
    if overlay_info_file.exists():
        try:
            with overlay_info_file.open() as f:
                infos = cast('dict[str, Any]', json.load(f))
        except Exception:
            pass

    viewport_used = all(k in infos for k in ("width", "height", "top", "left", "bottom", "right")) and not shaderBezel
    game_ratio = float(gameResolution["width"]) / float(gameResolution["height"])
    bezel_need_adaptation = False

    if viewport_used:
        if gameResolution["width"] != infos["width"] or gameResolution["height"] != infos["height"]:
            if game_ratio < 1.6 and gunsBordersSize is None:
                return
            bezel_need_adaptation = True
        retroarchConfig['aspect_ratio_index'] = str(ratioIndexes.index("custom"))
    else:
        if game_ratio < 1.6 and gunsBordersSize is None:
            return
        try:
            infos["width"], infos["height"] = bezelsUtil.fast_image_size(overlay_png_file)
            infos["top"] = int(infos["height"] * 2 / 1080)
            infos["left"] = int(infos["width"] * 241 / 1920)
            infos["bottom"] = int(infos["height"] * 2 / 1080)
            infos["right"] = int(infos["width"] * 241 / 1920)
            bezel_need_adaptation = True
        except Exception:
            pass
        if gameResolution["width"] == infos["width"] and gameResolution["height"] == infos["height"]:
            bezel_need_adaptation = False

    if not shaderBezel:
        retroarchConfig['input_overlay_enable'] = "true"
    retroarchConfig['input_overlay_scale'] = "1.0"
    retroarchConfig['input_overlay'] = RETROARCH_OVERLAY_CONFIG
    retroarchConfig['input_overlay_hide_in_menu'] = "true"
    retroarchConfig['input_overlay_opacity'] = infos.get("opacity", 1.0)

    bias = retroarchConfig["aspect_ratio_index"] != str(ratioIndexes.index("custom"))
    retroarchConfig["video_viewport_bias_x"] = "0.500000" if bias else "0.000000"
    retroarchConfig["video_viewport_bias_y"] = "0.500000" if bias else "0.000000"

    bezel_stretch = system.config.get_bool('bezel_stretch')
    tattoo_output_png = Path("/tmp/bezel_tattooed.png")
    qrcode_output_png = Path("/tmp/bezel_qrcode.png")

    if bezel_need_adaptation:
        wratio = gameResolution["width"] / float(infos["width"])
        hratio = gameResolution["height"] / float(infos["height"])
        if gameResolution["width"] < infos["width"] or gameResolution["height"] < infos["height"]:
            bezel_stretch = True

        output_png_file = Path("/tmp/bezel_per_game.png") if bezel_game else Path("/tmp") / f"{overlay_png_file.stem}_adapted.png"
        create_new = True
        if not bezel_game and system.config.get('bezel.tattoo', '0') == "0" and system.config.get('bezel.qrcode', '0') == "0" and output_png_file.exists():
            create_new = False

        if create_new:
            try:
                bezelsUtil.padImage(overlay_png_file, output_png_file, gameResolution["width"], gameResolution["height"], infos["width"], infos["height"], bezel_stretch)
            except Exception as e:
                _logger.debug("Failed to create adapted bezel: %s", e)
                return
        overlay_png_file = output_png_file
        if system.config.get('bezel.tattoo', '0') != "0":
            bezelsUtil.tatooImage(overlay_png_file, tattoo_output_png, system)
            overlay_png_file = tattoo_output_png
        if system.config.get('bezel.qrcode', '0') != "0" and (cheevos_id := system.es_game_info.get("cheevosId", "0")) != "0":
            bezelsUtil.addQRCode(overlay_png_file, qrcode_output_png, cheevos_id, system)
            overlay_png_file = qrcode_output_png

        if bezel_stretch:
            borderx = 0
            viewportRatio = float(infos["width"]) / float(infos["height"])
            if viewportRatio - game_ratio > 0.01:
                borderx = (infos["width"] - int(infos["width"] * game_ratio / viewportRatio)) // 2
            retroarchConfig['custom_viewport_x'] = int(round((infos["left"] - borderx / 2) * wratio))
            retroarchConfig['custom_viewport_y'] = int(round(infos["top"] * hratio))
            retroarchConfig['custom_viewport_width'] = int(round((infos["width"] - infos["left"] - infos["right"] + borderx) * wratio))
            retroarchConfig['custom_viewport_height'] = int(round((infos["height"] - infos["top"] - infos["bottom"]) * hratio))
        else:
            xoffset = gameResolution["width"] - (infos["width"] * wratio)
            yoffset = gameResolution["height"] - (infos["height"] * hratio)
            retroarchConfig['custom_viewport_x'] = int(round(infos["left"] * wratio + xoffset / 2))
            retroarchConfig['custom_viewport_y'] = int(round(infos["top"] * hratio + yoffset / 2))
            retroarchConfig['custom_viewport_width'] = int(round((infos["width"] - infos["left"] - infos["right"]) * wratio))
            retroarchConfig['custom_viewport_height'] = int(round((infos["height"] - infos["top"] - infos["bottom"]) * hratio))
    else:
        if viewport_used:
            retroarchConfig['custom_viewport_x'] = infos["left"]
            retroarchConfig['custom_viewport_y'] = infos["top"]
            retroarchConfig['custom_viewport_width'] = infos["width"] - infos["left"] - infos["right"]
            retroarchConfig['custom_viewport_height'] = infos["height"] - infos["top"] - infos["bottom"]
        retroarchConfig['video_message_pos_x'] = infos.get("messagex", 0.0)
        retroarchConfig['video_message_pos_y'] = infos.get("messagey", 0.0)

    if gunsBordersSize is not None:
        output_png_file = Path("/tmp/bezel_gunborders.png")
        innerSize, outerSize = bezelsUtil.gunBordersSize(gunsBordersSize)
        bezelsUtil.gunBorderImage(overlay_png_file, output_png_file, gunsBordersRatio, innerSize, outerSize, bezelsUtil.gunsBordersColorFomConfig(system.config))
        overlay_png_file = output_png_file

    writeBezelCfgConfig(RETROARCH_OVERLAY_CONFIG, overlay_png_file)

    if shaderBezel:
        shaderBezelPath = SHADER_BEZELS_DIR
        shaderBezelFile = shaderBezelPath / 'bezel.png'
        if not shaderBezelPath.exists():
            shaderBezelPath.mkdir(parents=True)
        if shaderBezelFile.exists():
            shaderBezelFile.unlink()
        shaderBezelFile.symlink_to(overlay_png_file)


def isLowResolution(gameResolution: Resolution, /) -> bool:
    return gameResolution["width"] < 480 or gameResolution["height"] < 480


def writeBezelCfgConfig(cfgFile: Path, overlay_png_file: Path, /) -> None:
    with cfgFile.open("w") as fd:
        fd.write("overlays = 1\n")
        fd.write(f'overlay0_overlay = "{overlay_png_file}"\n')
        fd.write("overlay0_full_screen = true\n")
        fd.write("overlay0_descs = 0\n")