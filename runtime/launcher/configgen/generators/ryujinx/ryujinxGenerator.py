from __future__ import annotations

from collections import defaultdict
import logging
import glob
import os
import re
import shutil
import subprocess
import json
import stat
import hashlib
from ctypes import create_string_buffer
from shutil import copyfile
from pathlib import Path
from typing import TYPE_CHECKING

import sdl2
from sdl2 import joystick

from runtime.retrobox_paths import (
    DEFAULTS_DIR,
    SAVES,
    configure_emulator,
    ensure_symlink,
    mkdir_if_not_exists
)

from ...controller import generate_sdl_game_controller_config

from ... import Command

from ..Generator import Generator
from ..eden.edenPaths import SWITCH_FIRMWARE, SWITCH_KEYS, SWITCH_MODS_DIR, SWITCH_ROMS
from .ryujinxPaths import (
    _RYUJINX_XDG,
    RYUJINX_BIN,
    RYUJINX_BIS,
    RYUJINX_CONFIG,
    RYUJINX_CONFIG_FILE,
    RYUJINX_CONFIG_FILE_BFR,
    RYUJINX_CONFIG_FILE_TPL,
    RYUJINX_MODS_LINK,
    RYUJINX_SAVE_BASE,
    RYUJINX_SYSTEM_CONFIG_DIR,
    RYUJINX_SYSTEM_DIR,
    RYUJINX_USER_DIR,
    RYUJINX_SYSTEM_SAVES,
    RYUJINX_USER_SAVES
)
from ...input import Input

_logger = logging.getLogger(__name__)

NINTENDO_GUIDS = {
    "050000007e0500000620000001800000",
    "050000007e0500000720000001800000",
    "050000007e0500000920000001800000",
}

if TYPE_CHECKING:
    from runtime.launcher.configgen.batoceraTypes import HotkeysContext

# copiar todo lo de una carpeta a otra (sincronizar .keys)
def sync_keys(src_dir: Path, dst_dir: Path):
    if not src_dir.is_dir():
        return

    dst_dir.mkdir(parents=True, exist_ok=True)

    for f in src_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, dst_dir / f.name)

# calcular el checksum de todo un directorio - para ver integridad de firmware
def compute_dir_checksum(path: Path) -> str:
    files = sorted(p for p in path.rglob("*") if p.is_file())
    h = hashlib.sha256()

    for f in files:
        h.update(f.read_bytes())

    return h.hexdigest()

# sincronizar firmware de la carpeta bios con lo que necesita ryujinx (carpetas con 00)
def sync_firmware(src: Path, registered: Path, checksum_file: Path):
    if not src.is_dir():
        return

    new_checksum = compute_dir_checksum(src)

    old_checksum = None
    if checksum_file.exists():
        old_checksum = checksum_file.read_text().strip()

    if new_checksum == old_checksum:
        return  # nada que hacer

    # rebuild
    if registered.exists():
        shutil.rmtree(registered)

    registered.mkdir(parents=True, exist_ok=True)

    for f in src.glob("*.nca"):
        dst_dir = registered / f.name
        dst_dir.mkdir()
        shutil.copy2(f, dst_dir / "00")

    checksum_file.parent.mkdir(parents=True, exist_ok=True)
    checksum_file.write_text(new_checksum)

def getCurrentCard() -> str | None:
    proc = subprocess.Popen([f"{DEFAULTS_DIR}/data/switch/detectvideo.sh"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    for val in out.decode().splitlines():
        return val # return the first line

def sdlmapping_to_controller(mapping, guid):

    sdl_to_batoinputmapping = {
        'a': 'b',
        'b': 'a',
        'y': 'x',
        'x': 'y',
        'lefttrigger': 'l2',
        'righttrigger': 'r2',
        'leftstick': 'l3',
        'rightstick': 'r3',
        'leftshoulder': 'pageup',
        'rightshoulder': 'pagedown',
        'start': 'start',
        'back': 'select',
        'dpup': 'up',
        'dpdown': 'down',
        'dpleft': 'left',
        'dpright': 'right',
        'lefty': 'joystick1up',
        'leftx': 'joystick1left',
        'righty': 'joystick2up',
        'rightx': 'joystick2left',
        'guide':  'hotkey'
    }

    elements = mapping.split(',')

    current_controller = {
        "guid": guid,
        "mapping": mapping,
        "platform": "",
        "inputs": {}
    }

    for element in elements[2:]:
        if not element:
            continue

        if element.startswith('platform:'):
            current_controller["platform"] = element[9:]  # Extraire après "platform:"
        elif ':' in element:
            logical_name, physical_mapping = element.split(':', 1)

            input_type = "unknown"
            clean_value = physical_mapping  # Valeur par défaut

            if physical_mapping.startswith('b'):
                input_type = "button"
                clean_value = physical_mapping[1:]  # Enlever le 'b'
            elif physical_mapping.startswith('a'):
                input_type = "axis"
                clean_value = physical_mapping[1:]  # Enlever le 'a'
            elif physical_mapping.startswith('h'):
                input_type = "hat"
                # Pour les hats, on conserve la partie après le 'h' qui contient des informations importantes
                clean_value = physical_mapping[1:]  # Enlever le 'h'
                clean_value_mask, clean_value = clean_value.split('.')

            if logical_name in sdl_to_batoinputmapping:
                logical_name = sdl_to_batoinputmapping[logical_name]

            input = Input(name=logical_name, type=input_type, id=clean_value, value=1, code=0 )
            current_controller["inputs"][logical_name] = input

    return current_controller

def evdev_to_hidraw():

    evdev_hidraw = {}

    for hid_path in glob.glob('/sys/class/hidraw/hidraw*'):
        # Obtenir le chemin du périphérique
        hid_dev = os.path.realpath(os.path.join(hid_path, "device"))

        events = []
        for root, dirs, files in os.walk(hid_dev):
            for dir in dirs:
                if dir.startswith("event"):
                    event_path = os.path.join(root, dir)
                    if "/input" in event_path and "/event" in event_path:
                        events.append(event_path)

        if events:
            for ev in events:
                ev_name = os.path.basename(ev)
                hid_name = os.path.basename(hid_path)
                evdev_hidraw[f"/dev/input/{ev_name}"] = f"/dev/{hid_name}"
    return evdev_hidraw

def detect_bus_from_hidraw(hidraw_path: str):
    # pass /dev/hidrawx
    hidraw_device = os.path.basename(hidraw_path)
    sysfs_path = f"/sys/class/hidraw/{hidraw_device}/device"

    if not os.path.exists(sysfs_path):
        return f"Device {hidraw_device} not found in sysfs"

    # Resolve the real path (follows symlinks)
    try:
        real_device_path = os.path.realpath(sysfs_path)
        bus_prefix = os.path.basename(real_device_path).split(":")[0]
    except Exception as e:
        return f"Error reading device path: {e}"

    return bus_prefix[2:]

def list_sdl_gamepads(sdlversion):

    os.environ["SDL_JOYSTICK_HIDAPI"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS4"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_PS5"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_SWITCH"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_XBOX"] = "1"
    os.environ["SDL_JOYSTICK_HIDAPI_STEAMDECK"] = "0"

    sdl2.SDL_ClearError()

    if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER) != 0:
        _logger.error("SDL init failed: %s", sdl2.SDL_GetError().decode())
        return {}

    sdl_devices = {}

    count = joystick.SDL_NumJoysticks()

    for i in range(count):

        if sdl2.SDL_IsGameController(i) != 1:
            continue

        pad = sdl2.SDL_GameControllerOpen(i)

        if not pad:
            continue

        try:

            # IMPORTANTE:
            # usar DeviceGUID y NO JoystickGUID
            guid = joystick.SDL_JoystickGetDeviceGUID(i)

            buff = create_string_buffer(33)

            joystick.SDL_JoystickGetGUIDString(
                guid,
                buff,
                33
            )

            guidstring = (
                bytes(buff)
                .decode("utf-8")
                .split('\x00', 1)[0]
                .lower()
            )

            guidstring = guidstring.replace("-", "").strip()

            name = sdl2.SDL_GameControllerName(pad)

            if isinstance(name, bytes):
                name = name.decode()

            mapping = sdl2.SDL_GameControllerMapping(pad)

            if isinstance(mapping, bytes):
                mapping = mapping.decode()

            try:
                joy_path = joystick.SDL_JoystickPathForIndex(i)

                if isinstance(joy_path, bytes):
                    joy_path = joy_path.decode()

            except Exception:
                joy_path = f"sdl-{i}"

            sdl_devices[joy_path] = {
                "guid": guidstring,
                "name": name,
                "mapping": mapping,
                "path": joy_path,
                "sdl_index": i,
            }
            _logger.warning(
                "SDL DEVICE index=%d name='%s' guid='%s'",
                i,
                name,
                guidstring
            )

        finally:
            sdl2.SDL_GameControllerClose(pad)

    sdl2.SDL_Quit()

    return sdl_devices

class RyujinxGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "ryujinx-emu",
            "keys": { "menu": "KEY_F4"}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        _logger.warning("DEBUG: generate() llamado, emulator=%s", system.config['emulator'])
        script = DEFAULTS_DIR / "data/switch/detectvideo.sh"
        st = script.stat()
        script.chmod(st.st_mode | stat.S_IEXEC)

        mkdir_if_not_exists(RYUJINX_CONFIG)

        copyfile(RYUJINX_CONFIG_FILE_TPL, RYUJINX_CONFIG_FILE)

        # Crear estructura base
        mkdir_if_not_exists(RYUJINX_BIS)
        mkdir_if_not_exists(RYUJINX_BIS / "system/Contents")

        # Firmware + keys
        sync_keys(SWITCH_KEYS, RYUJINX_SYSTEM_CONFIG_DIR)

        sync_firmware(
            SWITCH_FIRMWARE,
            RYUJINX_SYSTEM_DIR / "Contents/registered",
            RYUJINX_CONFIG / "checksum_firmware.txt"
        )
        
        # Saves base
        mkdir_if_not_exists(RYUJINX_SAVE_BASE)

        # USER SAVE
        mkdir_if_not_exists(RYUJINX_USER_SAVES)
        ensure_symlink(RYUJINX_USER_SAVES, RYUJINX_USER_DIR)

        # SYSTEM SAVE
        mkdir_if_not_exists(RYUJINX_SYSTEM_SAVES)
        ensure_symlink(RYUJINX_SYSTEM_SAVES, RYUJINX_SYSTEM_DIR / "save")

        # MODS
        mkdir_if_not_exists(SWITCH_MODS_DIR)
        ensure_symlink(SWITCH_MODS_DIR, RYUJINX_MODS_LINK)

        _logger.debug("Controller mapping before: {}".format(generate_sdl_game_controller_config(playersControllers)))

        #Configuration update
        sdl_mapping = RyujinxGenerator.writeRyujinxConfig(f"{RYUJINX_CONFIG_FILE}", f"{RYUJINX_CONFIG_FILE_BFR}", f"{RYUJINX_CONFIG_FILE_TPL}", system, playersControllers)

        _logger.debug("Controller mapping after: {}".format(str(sdl_mapping)))

        environment = { 
                        "SDL_JOYSTICK_HIDAPI": "1",
                        "SDL_JOYSTICK_HIDAPI_XBOX": "1",
                        "SDL_JOYSTICK_HIDAPI_STEAMDECK" : "1",
                        "SDL_JOYSTICK_HIDAPI_PS4" : "1",
                        "SDL_JOYSTICK_HIDAPI_PS5" : "1",
                        "SDL_JOYSTICK_HIDAPI_SWITCH" : "1",
                        "SDL_GAMECONTROLLERCONFIG": sdl_mapping,
                        "DOTNET_EnableAlternateStackCheck":"1",
                        "XDG_CONFIG_HOME":f"{_RYUJINX_XDG}",
                        "XDG_DATA_HOME":f"{SAVES}",
        }

        commandArray = []
        commandArray.extend([f"{RYUJINX_BIN}"])
        if not configure_emulator(rom):
            commandArray.extend([rom])

        return Command.Command(array=commandArray, env=environment)

    @staticmethod
    def sdl_guid_to_ryujinx_guid(sdl_guid):
        g = sdl_guid.lower().replace('-', '')
        if len(g) != 32:
            return sdl_guid
        b = [g[i:i+2] for i in range(0, 32, 2)]

        bus_le = b[0:2]
        b[0] = '00'
        b[1] = '00'
        b[2] = bus_le[1]
        b[3] = bus_le[0]
        b[4], b[5] = b[5], b[4]
        return ''.join(b)
    
    @staticmethod
    def writeRyujinxConfig(RyujinxConfigFile, RyujinxConfigFileBefore, RyujinxConfigTemplateFile, system, playersControllers):
        _logger.debug(RyujinxConfigTemplateFile)
        data = {}

        if os.path.exists(f"{RYUJINX_CONFIG_FILE_TPL}"):
            with open(f"{RYUJINX_CONFIG_FILE_TPL}", "r+", encoding="utf-8") as read_file:
                data = json.load(read_file)

        # if manual controller configuration, keep current config
        if system.isOptSet('ryu_auto_controller_config') and system.config["ryu_auto_controller_config"] == "0":
            if os.path.exists(f"{RYUJINX_CONFIG_FILE}"):
                with open(f"{RYUJINX_CONFIG_FILE}", "r+", encoding="utf-8") as read_file:
                    current_data = json.load(read_file)
                    data['input_config'] = current_data['input_config']

        if system.isOptSet('res_scale'):
            data['res_scale'] = int(system.config["res_scale"])
        else:
            data['res_scale'] = 1

        if system.isOptSet('max_anisotropy'):
            data['max_anisotropy'] = int(system.config["max_anisotropy"])
        else:
            data['max_anisotropy'] = -1 

        if system.isOptSet('aspect_ratio'):
            data['aspect_ratio'] = system.config["aspect_ratio"]
        else:
            data['aspect_ratio'] = 'Fixed16x9'

        if system.isOptSet('system_language'):
            data['system_language'] = system.config["system_language"]
        else:
            data['system_language'] = 'AmericanEnglish'

        if system.isOptSet('system_region'):
            data['system_region'] = system.config["system_region"]
        else:
            data['system_region'] = 'USA'

        # discord integration
        data['enable_discord_integration'] = system.config.get_bool('discordrpc', True, return_values=(True, False))
        
        # docked mode
        data['docked_mode'] = system.config.get_bool('ryu_docked_mode', True, return_values=(True, False))

        # V-Sync
        data['enable_vsync'] = system.config.get_bool("use_vsync", True, return_values=(True, False))

        # graphics backend
        if system.isOptSet('ryu_backend'):
            data['graphics_backend'] = system.config["ryu_backend"]
        else:
            data['graphics_backend'] = 'Vulkan'

        data['language_code'] = str(get_lang_from_sys_env())
        data['game_dirs'] = [f"{SWITCH_ROMS}"]

        sdl_mapping = generate_sdl_game_controller_config(playersControllers)

        if not system.isOptSet('ryu_auto_controller_config') or system.config["ryu_auto_controller_config"] != "0":
            debugcontrollers = False
            sdl_mapping = ""

            # get the evdev->hidraw mapping
            evdev_hidraw = evdev_to_hidraw()
            # get sdllib hidapi/hidraw + evdev guid
            sdl_gamepads = list_sdl_gamepads(2)

            if debugcontrollers:
                _logger.debug("=====================================================Start Bato Controller Debug Info=========================================================")
                for index, controller in enumerate(playersControllers, start=0):
                    _logger.debug("Controller configName: {}".format(controller.name))
                    _logger.debug("Controller index: {}".format(controller.index))
                    _logger.debug("Controller real_name: {}".format(controller.real_name))
                    _logger.debug("Controller device_path: {}".format(controller.device_path))
                    _logger.debug("Controller player: {}".format(controller.player_number))
                    _logger.debug("Controller GUID: {}".format(controller.guid))
                    _logger.debug("")
                _logger.debug("=====================================================End Bato Controller Debug Info===========================================================")
                _logger.debug("")

            input_config = []

            # guid resolution for all controllers
            pad_pure_guid = {}
            pad_sdl_index = {}

            for controller in playersControllers:
                matched_sdl_ctrl = None

                hidraw_path = evdev_hidraw.get(controller.device_path)
                if hidraw_path and hidraw_path in sdl_gamepads:
                    matched_sdl_ctrl = sdl_gamepads[hidraw_path]
                elif controller.device_path in sdl_gamepads:
                    matched_sdl_ctrl = sdl_gamepads[controller.device_path]

                found_sdl_guid = matched_sdl_ctrl.get("guid") if matched_sdl_ctrl else None
                pad_sdl_index[id(controller)] = matched_sdl_ctrl.get("sdl_index", 0) if matched_sdl_ctrl else 0

                def is_valid_sdl_guid(g):
                    if not g:
                        return False
                    g = re.sub(r'[^0-9a-f]', '', str(g).lower())
                    if len(g) != 32:
                        return False
                    if g.startswith("00000000"):
                        return False
                    return True

                controller_guid = getattr(controller, 'guid', None)

                if is_valid_sdl_guid(found_sdl_guid):
                    pure_guid = found_sdl_guid
                elif is_valid_sdl_guid(controller_guid):
                    pure_guid = controller_guid
                else:
                    pure_guid = "00000000000000000000000000000000"

                pure_guid = re.sub(r'[^0-9a-f]', '', str(pure_guid).lower())
                pure_guid = pure_guid[:32].ljust(32, "0")
                pure_guid = RyujinxGenerator.sdl_guid_to_ryujinx_guid(pure_guid)
                pad_pure_guid[id(controller)] = pure_guid

            # relative idx per guid
            guid_groups = defaultdict(list)
            for controller in sorted(playersControllers, key=lambda c: pad_sdl_index[id(c)]):
                guid_groups[pad_pure_guid[id(controller)]].append(controller)

            controller_idx_map = {}
            for guid, group in guid_groups.items():
                for idx, controller in enumerate(group):
                    controller_idx_map[id(controller)] = idx

            # --- FASE 3: construir input_config ordenado por player_number ---
            for controller in sorted(playersControllers, key=lambda c: int(c.player_number)):
                pure_guid = pad_pure_guid[id(controller)]
                current_idx = controller_idx_map[id(controller)]

                formatted_guid = (
                    f"{pure_guid[0:8]}-"
                    f"{pure_guid[8:12]}-"
                    f"{pure_guid[12:16]}-"
                    f"{pure_guid[16:20]}-"
                    f"{pure_guid[20:32]}"
                )

                final_guid = f"{current_idx}-{formatted_guid}"

                left_joycon_stick = {}
                left_joycon_stick['joystick'] = "Left"
                left_joycon_stick['rotate90_cw'] = bool(0)
                left_joycon_stick['invert_stick_x'] = bool(0)
                left_joycon_stick['invert_stick_y'] = bool(0)
                left_joycon_stick['stick_button'] = "LeftStick"

                right_joycon_stick = {}
                right_joycon_stick['joystick'] = "Right"
                right_joycon_stick['rotate90_cw'] = bool(0)
                right_joycon_stick['invert_stick_x'] = bool(0)
                right_joycon_stick['invert_stick_y'] = bool(0)
                right_joycon_stick['stick_button'] = "RightStick"

                motion = {}
                motion['motion_backend'] = "GamepadDriver"
                motion['sensitivity'] = 100
                motion['gyro_deadzone'] = 1
                motion['enable_motion'] = bool(1)

                rumble = {}
                rumble['strong_rumble'] = 1
                rumble['weak_rumble'] = 1
                rumble['enable_rumble'] = bool(1)

                left_joycon = {}
                left_joycon['button_minus'] = "Back"
                left_joycon['button_l'] = "LeftShoulder"
                left_joycon['button_zl'] = "LeftTrigger"
                left_joycon['button_sl'] = "SingleLeftTrigger0"
                left_joycon['button_sr'] = "SingleRightTrigger0"
                left_joycon['dpad_up'] = "DpadUp"
                left_joycon['dpad_down'] = "DpadDown"
                left_joycon['dpad_left'] = "DpadLeft"
                left_joycon['dpad_right'] = "DpadRight"

                right_joycon = {}
                right_joycon['button_plus'] = "Start"
                right_joycon['button_r'] = "RightShoulder"
                right_joycon['button_zr'] = "RightTrigger"
                right_joycon['button_sl'] = "SingleLeftTrigger1"
                right_joycon['button_sr'] = "SingleRightTrigger1"

                ryu_inverse_button = system.config.get('ryu_inverse_button', 'false').lower() == 'true'
                if controller.real_name and ( \
                    "Nintendo" in controller.real_name or controller.guid in NINTENDO_GUIDS):
                    right_joycon['button_x'] = "X"
                    right_joycon['button_b'] = "B"
                    right_joycon['button_y'] = "Y"
                    right_joycon['button_a'] = "A"
                elif ryu_inverse_button:
                    right_joycon['button_x'] = "X"
                    right_joycon['button_b'] = "B"
                    right_joycon['button_y'] = "Y"
                    right_joycon['button_a'] = "A"
                else:
                    right_joycon['button_x'] = "Y"
                    right_joycon['button_b'] = "A"
                    right_joycon['button_y'] = "X"
                    right_joycon['button_a'] = "B"

                cvalue = {}
                cvalue['controller_type'] = "ProController"
                cvalue['left_joycon_stick'] = left_joycon_stick
                cvalue['right_joycon_stick'] = right_joycon_stick
                cvalue['deadzone_left'] = 0.1
                cvalue['deadzone_right'] = 0.1
                cvalue['range_left'] = 1
                cvalue['range_right'] = 1
                cvalue['trigger_threshold'] = 0.5
                cvalue['motion'] = motion
                cvalue['rumble'] = rumble
                cvalue['led'] = {
                    'enable_led': False,
                    'turn_off_led': False,
                    'use_rainbow': False,
                    'led_color': 0
                }
                cvalue['left_joycon'] = left_joycon
                cvalue['right_joycon'] = right_joycon
                cvalue['version'] = 1
                cvalue['backend'] = "GamepadSDL2"
                cvalue['id'] = final_guid
                cvalue['name'] = f"{getattr(controller, 'real_name', 'Gamepad')} ({str(current_idx)})"
                cvalue['player_index'] = "Player" + str(int(controller.player_number))

                input_config.append(cvalue)

            data['input_config'] = input_config

        # Resolution Scale
        if system.isOptSet('ryu_resolution_scale'):
            if system.config["ryu_resolution_scale"] in {'1.0', '2.0', '3.0', '4.0', 1.0, 2.0, 3.0, 4.0}:
                data['res_scale_custom'] = 1
                if system.config["ryu_resolution_scale"] in {'1.0', 1.0}:
                    data['res_scale'] = 1
                if system.config["ryu_resolution_scale"] in {'2.0', 2.0}:
                    data['res_scale'] = 2
                if system.config["ryu_resolution_scale"] in {'3.0', 3.0}:
                    data['res_scale'] = 3
                if system.config["ryu_resolution_scale"] in {'4.0', 4.0}:
                    data['res_scale'] = 4
            else:
                data['res_scale_custom'] = float(system.config["ryu_resolution_scale"])
                data['res_scale'] = -1
        else:
            data['res_scale_custom'] = 1
            data['res_scale'] = 1

        # Texture Recompression
        if system.isOptSet('ryu_texture_recompression'):
            if system.config["ryu_texture_recompression"] in {"true", "1", 1}:
                data['enable_texture_recompression'] = True
            elif system.config["ryu_texture_recompression"] in {"false", "0", 0}:
                data['enable_texture_recompression'] = False
        else:
            data['enable_texture_recompression'] = False

        with open(RyujinxConfigFile, "w", encoding="utf-8") as outfile:
            outfile.write(json.dumps(data, indent=2))

        # just to be able to do diff to be sure than the emu is not changing values
        with open(RyujinxConfigFileBefore, "w", encoding="utf-8") as outfile:
            outfile.write(json.dumps(data, indent=2))

        return sdl_mapping

def get_lang_from_sys_env():
    """Checks the current system locale and if it's available for the emulator and games.
    If not, we fallback to en_US.
    """

    lang = os.environ['LANG'][:5]
    available_langs = [
        "en_US",
        "pt_BR",
        "es_ES",
        "fr_FR",
        "de_DE",
        "it_IT",
        "el_GR",
        "tr_TR",
        "zh_CN"
    ]

    if lang in available_langs:
        return lang
    else:
        return "en_US"
