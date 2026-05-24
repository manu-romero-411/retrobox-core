from __future__ import annotations

import logging
import os
import sys
import glob
import pathlib
from pathlib import Path
from typing import TYPE_CHECKING

from configgen import Command as Command
from configgen.batoceraPaths import _SYSTEM_LOCAL_BIN, CONFIGS, DEFAULTS_DIR, ROMS, SAVES, configure_emulator
from configgen.generators.Generator import Generator
from configgen.utils.configparser import CaseSensitiveRawConfigParser
from configgen.input import Input
from datetime import datetime

from configgen.generators.eden.edenPaths import SWITCH_DLC_DIR, EDEN_BIN, SWITCH_ROMS, SWITCH_UPDATE_DIR, setup_eden_environments

os.environ["PYSDL2_DLL_PATH"] = "/usr/lib/x86_64-linux-gnu"

import sdl2
from sdl2 import joystick
from ctypes import create_string_buffer

eslog = logging.getLogger(__name__)

if TYPE_CHECKING:
    from configgen.batoceraTypes import HotkeysContext

class DictToObject:
    def __init__(self, dictionary):
        for key, value in dictionary.items():
            if isinstance(value, dict):
                value = DictToObject(value)
            setattr(self, key, value)

def switch_log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [SWITCH-DEBUG] {msg}", flush=True)

def log_stderr(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} [SWITCH-DEBUG] {msg}", file=sys.stdout)	

def fix_guid_for_eden(guid):
    # SDL del sistema modifica bytes 2-5, eden espera el GUID SDL estándar
    # 03004e526f0e... → 030000006f0e...
    return guid[:4] + "0000" + guid[8:]

def hidraw_get_guid(devpath):
    try:
        vid = pid = None
        p = devpath
        while p != "/" and p:
            if os.path.exists(os.path.join(p, "idVendor")):
                with open(os.path.join(p, "idVendor")) as f:
                    vid = f.read().strip()
                with open(os.path.join(p, "idProduct")) as f:
                    pid = f.read().strip()
                break
            p = os.path.dirname(p)
        if not vid or not pid:
            return "00000000000000000000000000000000"
        return f"{vid}{pid}000000000000000000000000"
    except:
        return "00000000000000000000000000000000"

def list_hidraw_devices():
    devices = []
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        dev = os.path.basename(h)
        devpath = os.path.realpath(os.path.join(h, "device"))
        name = "unknown"
        try:
            with open(os.path.join(devpath, "uevent")) as f:
                for line in f:
                    if line.startswith("HID_NAME="):
                        name = line.strip().split("=", 1)[1]
        except:
            pass
        bus = os.path.basename(devpath).split(":")[0]
        guid = hidraw_get_guid(devpath)
        devices.append({
            "hidraw": f"/dev/{dev}",
            "name": name,
            "bus": bus,
            "guid": guid
        })
    return devices

def map_hidraw_to_evdev():
    mapping = {}
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        hid = os.path.basename(h)
        devpath = os.path.realpath(os.path.join(h, "device"))
        for root, dirs, files in os.walk(devpath):
            for d in dirs:
                if d.startswith("event"):
                    mapping[f"/dev/{hid}"] = f"/dev/input/{d}"
    return mapping

def sdlmapping_to_controller(mapping, guid):
    sdl_to_batoinputmapping = {
        'a': 'b', 'b': 'a', 'y': 'x', 'x': 'y',
        'lefttrigger': 'l2', 'righttrigger': 'r2',
        'leftstick': 'l3', 'rightstick': 'r3',
        'leftshoulder': 'pageup', 'rightshoulder': 'pagedown',
        'start': 'start', 'back': 'select',
        'dpup': 'up', 'dpdown': 'down', 'dpleft': 'left', 'dpright': 'right',
        'lefty': 'joystick1up', 'leftx': 'joystick1left',
        'righty': 'joystick2up', 'rightx': 'joystick2left',
        'guide':  'hotkey'
    }

    elements = mapping.split(',')
    current_controller = {"guid": guid, "platform": "", "inputs": {}}

    for element in elements[2:]:
        if not element:
            continue

        if element.startswith('platform:'):
            current_controller["platform"] = element[9:]
        elif ':' in element:
            logical_name, physical_mapping = element.split(':', 1)
            input_type = "unknown"
            clean_value = physical_mapping

            if physical_mapping.startswith('b'):
                input_type = "button"
                clean_value = physical_mapping[1:]
                input_obj = Input(name=logical_name, type=input_type, id=clean_value, value=1, code=0)
            elif physical_mapping.startswith('a'):
                input_type = "axis"
                clean_value = physical_mapping[1:]
                input_obj = Input(name=logical_name, type=input_type, id=clean_value, value=1, code=0)
            elif physical_mapping.startswith('h'):
                input_type = "hat"
                clean_value = physical_mapping[1:]
                clean_value_mask, clean_value_dir = clean_value.split('.')
                input_obj = Input(name=logical_name, type=input_type, id=clean_value_mask, value=clean_value_dir, code=0)
            else:
                continue

            if logical_name in sdl_to_batoinputmapping:
                logical_name = sdl_to_batoinputmapping[logical_name]
                input_obj = Input(name=logical_name, type=input_obj.type, id=input_obj.id, value=input_obj.value, code=0)

            current_controller["inputs"][logical_name] = input_obj

    return current_controller

def evdev_to_hidraw():
    evdev_hidraw = {}
    for hid_path in glob.glob('/sys/class/hidraw/hidraw*'):
        hid_dev = os.path.realpath(os.path.join(hid_path, "device"))
        events = []
        for root, dirs, files in os.walk(hid_dev):
            for directory in dirs:
                if directory.startswith("event"):
                    event_path = os.path.join(root, directory)
                    if "/input" in event_path and "/event" in event_path:
                        events.append(event_path)
        if events:
            for ev in events:
                ev_name = os.path.basename(ev)
                hid_name = os.path.basename(hid_path)
                evdev_hidraw[f"/dev/input/{ev_name}"] = f"/dev/{hid_name}"
    return evdev_hidraw

def detect_bus_from_hidraw(hidraw_path: str):
    hidraw_device = os.path.basename(hidraw_path)
    sysfs_path = f"/sys/class/hidraw/{hidraw_device}/device"

    if not os.path.exists(sysfs_path):
        return f"Device {hidraw_device} not found in sysfs"

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
    os.environ["SDL_GAMECONTROLLERCONFIG_FILE"] = f"{DEFAULTS_DIR}/data/switch/sdl2/gamecontrollerdb.txt"
    
    sdl2.SDL_ClearError()
    try:
        sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER)
    except:
        print("An exception occurred")

    count = joystick.SDL_NumJoysticks()
    sdl_devices = {}

    for i in range(count):
        if sdl2.SDL_IsGameController(i) == 1:
            pad = sdl2.SDL_GameControllerOpen(i)
            joy_guid = joystick.SDL_JoystickGetDeviceGUID(i)
            buff = create_string_buffer(33)
            joystick.SDL_JoystickGetGUIDString(joy_guid, buff, 33)
            print("================================================================")
            print(f"GUID raw de SDL: {bytes(buff)}", flush=True)

            guidstring = ((bytes(buff)).decode()).split('\x00', 1)[0]

            print(f"GUID tras decode: {guidstring}", flush=True)
            print("================================================================")
            joy_path = joystick.SDL_JoystickPathForIndex(i).decode()

            if 'hidraw' in joy_path and sdlversion == 3:
                bustype = detect_bus_from_hidraw(joy_path)
                guidstring = bustype + guidstring[2:]

            mapping = sdl2.SDL_GameControllerMapping(pad)
            import pprint
            pprint.pprint(mapping)
            eslog.debug(str(mapping))
            controller = sdlmapping_to_controller(str(mapping), guidstring)
            sdl_devices[joy_path] = controller

    sdl2.SDL_Quit()
    return sdl_devices

def read_file_lower(path):
    try:
        return pathlib.Path(path).read_text().strip().lower()
    except FileNotFoundError:
        return ""

def is_steamdeck():
    pname = read_file_lower("/sys/class/dmi/id/product_name")
    if pname in ("jupiter", "galileo") or "steam deck" in pname:
        return True
    return False

class EdenGenerator(Generator):

    def getHotkeysContext(self) -> HotkeysContext:
        return {
            "name": "switch-emu",
            "keys": { "exit": ["KEY_LEFTALT", "KEY_F4"]}
        }

    def generate(self, system, rom, playersControllers, metadata, guns, wheels, gameResolution):
        eslog.warning("DEBUG: generate() llamado, emulator=%s", system.config['emulator'])
        emulator = system.config['emulator']

        sdlversion = 2

        # Invocar la creación modular de rutas y entornos symlink
        setup_eden_environments()

        # Forzamos la ruta real de configuración en Debian nativo (~/.config/eden/qt-config.ini o ~/.config/citron/qt-config.ini)
        config_name = "citron" if emulator == "citron-emu" else "eden"
        yuzuConfig = os.path.expanduser(f"{CONFIGS}/{config_name}/qt-config.ini")
        
        # El template lo seguimos buscando en la carpeta del script
        yuzuConfigTemplate = f'{DEFAULTS_DIR}/data/switch/qt-config.ini.template'
        EdenGenerator.writeYuzuConfig(yuzuConfig, yuzuConfigTemplate, system, playersControllers, sdlversion, emulator)

        commandArray = [f"{EDEN_BIN}"]

        if configure_emulator(rom):
            commandArray.extend(["-qlaunch"])
        else:
            commandArray.extend(["-f", "-g", str(rom)])

        environment = {
            "XDG_CONFIG_HOME":f"{CONFIGS}",
            "XDG_DATA_HOME":f"{SAVES}/switch",
            "SDL_JOYSTICK_HIDAPI": "1",
            "SDL_JOYSTICK_HIDAPI_STEAMDECK": "0",
            "SDL_JOYSTICK_HIDAPI_PS4": "1",
            "SDL_JOYSTICK_HIDAPI_PS5": "1",
            "SDL_JOYSTICK_HIDAPI_SWITCH": "1",
            "SDL_JOYSTICK_HIDAPI_XBOX": "1",
        }

        return Command.Command(array=commandArray, env=environment)
    
    @staticmethod
    def writeYuzuConfig(yuzuConfigFile, yuzuConfigTemplateFile, system, playersControllers, sdlversion, emulator):
        eslog.warning("DEBUG: writeYuzuConfig() llamado, nplayers=%d", len(playersControllers))        # pads

        yuzuButtonsMapping = {
             "button_a":      "a",
             "button_b":      "b",
             "button_x":      "x",
             "button_y":      "y",
             "button_dup":    "up",
             "button_ddown":  "down",
             "button_dleft":  "left",
             "button_dright": "right",
             "button_l":      "pageup",
             "button_r":      "pagedown",
             "button_plus":   "start",
             "button_minus":  "select",
             "button_slleft": "pageup",
             "button_srleft": "pagedown",
             "button_slright": "pageup",
             "button_srright": "pagedown",
             "button_zl":     "l2",
             "button_zr":     "r2",
             "button_lstick": "l3",
             "button_rstick": "r3",
             "button_home":   "hotkey"
        }

        yuzuAxisMapping = {
             "lstick":    "joystick1",
             "rstick":    "joystick2"
        }

        # ini file
        yuzuConfig = CaseSensitiveRawConfigParser()
        yuzuConfig.optionxform=str

        if os.path.exists(yuzuConfigFile):
            yuzuConfig.read(yuzuConfigFile)
        # Sinon première création depuis template
        elif os.path.exists(yuzuConfigTemplateFile):
            yuzuConfig.read(yuzuConfigTemplateFile)

    # UI section
        if not yuzuConfig.has_section("UI"):
            yuzuConfig.add_section("UI")

        yuzuConfig.set("UI", "enable_discord_presence", "true")
        yuzuConfig.set("UI", "enable_discord_presence\\default", "true")

        yuzuConfig.set("UI", "check_for_updates_on_start", "false")
        yuzuConfig.set("UI", "check_for_updates_on_start\\default", "false")

        if emulator == "citron-emu":
            yuzuConfig.set("UI", "UIGameList\\cache_game_list", "false")
            yuzuConfig.set("UI", "UIGameList\\cache_game_list\\default", "false")
        else:
            yuzuConfig.set("UI", "UIGameList\\cache_game_list", "true")
            yuzuConfig.set("UI", "UIGameList\\cache_game_list\\default", "true")

        # Common external path (dlc/update)
        yuzuConfig.set("UI", "Paths\\external_content_dirs\\size", "2")
        yuzuConfig.set("UI", "Paths\\external_content_dirs\\1\\path", f"{SWITCH_UPDATE_DIR}")
        yuzuConfig.set("UI", "Paths\\external_content_dirs\\2\\path", f"{SWITCH_DLC_DIR}")

        #citron shortcuts
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\size", "1")#adjust to number of shortcut sets
        #exit citron
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\name", "Exit citron")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\group", "Main Window")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\keyseq", "Ctrl+Q")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\controller_keyseq", "Minus+Plus")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\context", "1")
        yuzuConfig.set("UI", "Shortcuts\\shortcuts\\1\\repeat", "false")

        #exit eden
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\KeySeq", "Ctrl+Q")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Controller_KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Controller_KeySeq", "Home+Plus")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Context\\default", "true")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Exit%20eden\\Context", "1")

        #fullscreen eden
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\KeySeq", "F11")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Controller_KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Controller_KeySeq", "Home+B")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Context\\default", "true")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Fullscreen\\Context", "1")

        #pause eden
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\KeySeq", "F4")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Controller_KeySeq\\default", "false")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Controller_KeySeq", "")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Context\\default", "true")
        yuzuConfig.set("UI", "Shortcuts\\Main%20Window\\Continue\\Pause%20Emulation\\Context", "1")

        yuzuConfig.set("UI", "Paths\\romsPath", f"{SWITCH_ROMS}")
        yuzuConfig.set("UI", "Paths\\gamedirs\\1\\deep_scan", "true")
        yuzuConfig.set("UI", "Paths\\gamedirs\\1\\deep_scan\\default", "false")
        yuzuConfig.set("UI", "Paths\\gamedirs\\1\\expanded", "true")
        yuzuConfig.set("UI", "Paths\\gamedirs\\1\\expanded\\default", "true")
        yuzuConfig.set("UI", "Paths\\gamedirs\\1\\path", f"{SWITCH_ROMS}")
        yuzuConfig.set("UI", "Paths\\gamedirs\\size", "3")

        # Interface language (citron)
        if system.isOptSet('yuzu_intlanguage'):
            yuzuConfig.set("UI", "Paths\\language", system.config["yuzu_intlanguage"])
            yuzuConfig.set("UI", "Paths\\language\\default", "false")
        else:
            yuzuConfig.set("UI", "Paths\\language", "en")
            yuzuConfig.set("UI", "Paths\\language\\default", "true")

        # Single Window Mode
        if system.isOptSet('single_window'):
            yuzuConfig.set("UI", "singleWindowMode", system.config["single_window"])
            yuzuConfig.set("UI", "singleWindowMode\\default", "false")
        else:
            yuzuConfig.set("UI", "singleWindowMode", "true")
            yuzuConfig.set("UI", "singleWindowMode\\default", "true")

        # User Profile select on boot
        if system.isOptSet('user_profile'):
            yuzuConfig.set("UI", "select_user_on_boot", system.config["user_profile"])
            yuzuConfig.set("UI", "select_user_on_boot\\default", "false")
        else:
            yuzuConfig.set("UI", "select_user_on_boot", "true")
            yuzuConfig.set("UI", "select_user_on_boot\\default", "true")

        # Skip Citron animation/message
        yuzuConfig.set("UI", "showIntroAnimation", "false")
        yuzuConfig.set("UI", "showIntroAnimation\\default", "false")
        yuzuConfig.set("UI", "farewellShown", "true")
        yuzuConfig.set("UI", "farewellShown\\default", "false")

        # Confirm exit off
        yuzuConfig.set("UI", "confirmStop", "2")
        yuzuConfig.set("UI", "confirmStop\\default", "false")

    # Core section
        if not yuzuConfig.has_section("Core"):
            yuzuConfig.add_section("Core")

        # Multicore
        if system.isOptSet('multicore'):
            yuzuConfig.set("Core", "use_multi_core", system.config["multicore"])
            yuzuConfig.set("Core", "use_multi_core\\default", "false")
        else:
            yuzuConfig.set("Core", "use_multi_core", "true")
            yuzuConfig.set("Core", "use_multi_core\\default", "true")

        # Memory layout
        if system.isOptSet('yuzu_memory_layout'):
            yuzuConfig.set("Core", "memory_layout_mode", system.config["yuzu_memory_layout"])
            yuzuConfig.set("Core", "memory_layout_mode\\default", "false")
        else:
            yuzuConfig.set("Core", "memory_layout_mode", "0")
            yuzuConfig.set("Core", "memory_layout_mode\\default", "true")

    # Renderer section
        if not yuzuConfig.has_section("Renderer"):
            yuzuConfig.add_section("Renderer")

        # Extended Dynamic State Fix for V43 ZEN3
        if is_steamdeck():
            yuzuConfig.set("Renderer", "extended_dynamic_state", "0")
            yuzuConfig.set("Renderer", "extended_dynamic_state\\default", "false")
        # Aspect ratio
        if system.isOptSet('yuzu_ratio'):
            yuzuConfig.set("Renderer", "aspect_ratio", system.config["yuzu_ratio"])
            yuzuConfig.set("Renderer", "aspect_ratio\\default", "false")
        else:
            yuzuConfig.set("Renderer", "aspect_ratio", "0")
            yuzuConfig.set("Renderer", "aspect_ratio\\default", "true")

        # Graphical backend
        if system.isOptSet('yuzu_backend'):
            yuzuConfig.set("Renderer", "backend", system.config["yuzu_backend"])
            yuzuConfig.set("Renderer", "backend\\default", "false")
        else:
            yuzuConfig.set("Renderer", "backend", "1")
            yuzuConfig.set("Renderer", "backend\\default", "true")

        # Async Shader compilation
        if system.isOptSet('async_shaders'):
            yuzuConfig.set("Renderer", "use_asynchronous_shaders", system.config["async_shaders"])
            yuzuConfig.set("Renderer", "use_asynchronous_shaders\\default", "false")
        else:
            yuzuConfig.set("Renderer", "use_asynchronous_shaders", "false")
            yuzuConfig.set("Renderer", "use_asynchronous_shaders\\default", "true")

        # Assembly shaders
        if system.isOptSet('shaderbackend'):
            yuzuConfig.set("Renderer", "shader_backend", system.config["shaderbackend"])
            yuzuConfig.set("Renderer", "shader_backend\\default", "false")
        else:
            yuzuConfig.set("Renderer", "shader_backend", "0")
            yuzuConfig.set("Renderer", "shader_backend\\default", "true")

        # Async Gpu Emulation
        if system.isOptSet('async_gpu'):
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation", system.config["async_gpu"])
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation\\default", "false")
        else:
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation", "true")
            yuzuConfig.set("Renderer", "use_asynchronous_gpu_emulation\\default", "true")

        # NVDEC Emulation
        if system.isOptSet('nvdec_emu'):
            yuzuConfig.set("Renderer", "nvdec_emulation", system.config["nvdec_emu"])
            yuzuConfig.set("Renderer", "nvdec_emulation\\default", "false")
        else:
            yuzuConfig.set("Renderer", "nvdec_emulation", "2")
            yuzuConfig.set("Renderer", "nvdec_emulation\\default", "true")

        # Gpu Accuracy
        if system.isOptSet('gpuaccuracy'):
            yuzuConfig.set("Renderer", "gpu_accuracy", system.config["gpuaccuracy"])
        else:
            yuzuConfig.set("Renderer", "gpu_accuracy", "1")
        yuzuConfig.set("Renderer", "gpu_accuracy\\default", "false")

        # Vsync
        if system.isOptSet('vsync'):
            yuzuConfig.set("Renderer", "use_vsync", system.config["vsync"])
            yuzuConfig.set("Renderer", "use_vsync\\default", "false")
            if system.config["vsync"] == "2":
                yuzuConfig.set("Renderer", "use_vsync\\default", "true")
        else:
            yuzuConfig.set("Renderer", "use_vsync", "1")
            yuzuConfig.set("Renderer", "use_vsync\\default", "false")

        # Gpu cache garbage collection
        if system.isOptSet('gpu_cache_gc'):
            yuzuConfig.set("Renderer", "use_caches_gc", system.config["gpu_cache_gc"])
        else:
            yuzuConfig.set("Renderer", "use_caches_gc", "false")
        yuzuConfig.set("Renderer", "use_caches_gc\\default", "false")

        # Max anisotropy
        if system.isOptSet('anisotropy'):
            yuzuConfig.set("Renderer", "max_anisotropy", system.config["anisotropy"])
            yuzuConfig.set("Renderer", "max_anisotropy\\default", "false")
        else:
            yuzuConfig.set("Renderer", "max_anisotropy", "0")
            yuzuConfig.set("Renderer", "max_anisotropy\\default", "true")

        # Fullscreen mode
        if system.isOptSet('fullscreen_mode'):
            yuzuConfig.set("Renderer", "fullscreen_mode", system.config["fullscreen_mode"])
            yuzuConfig.set("Renderer", "fullscreen_mode\\default", "false")
        else:
            yuzuConfig.set("Renderer", "fullscreen_mode", "1")
            yuzuConfig.set("Renderer", "fullscreen_mode\\default", "true")

        if emulator == "citron-emu":
            # Resolution scaler
            if system.isOptSet('citron_resolution_scale'):
                print ("Use Resolution Scale for Citron:",system.config["citron_resolution_scale"], file=sys.stderr)
                yuzuConfig.set("Renderer", "resolution_setup", system.config["citron_resolution_scale"])
                yuzuConfig.set("Renderer", "resolution_setup\\default", "false")
            else:
                yuzuConfig.set("Renderer", "resolution_setup", "2")
                yuzuConfig.set("Renderer", "resolution_setup\\default", "true")
        else:        
            # Resolution scaler
            if system.isOptSet('resolution_scale'):
                print ("Use Resolution Scale for Eden :",system.config["resolution_scale"], file=sys.stderr)
                yuzuConfig.set("Renderer", "resolution_setup", system.config["resolution_scale"])
                yuzuConfig.set("Renderer", "resolution_setup\\default", "false")
            else:
                yuzuConfig.set("Renderer", "resolution_setup", "2")
                yuzuConfig.set("Renderer", "resolution_setup\\default", "true")

        # Scaling filter
        if system.isOptSet('scale_filter'):
            yuzuConfig.set("Renderer", "scaling_filter", system.config["scale_filter"])
            yuzuConfig.set("Renderer", "scaling_filter\\default", "false")
        else:
            yuzuConfig.set("Renderer", "scaling_filter", "1")
            yuzuConfig.set("Renderer", "scaling_filter\\default", "true")

        # FSR Quality
        if system.isOptSet('fsr_quality'):
            yuzuConfig.set("Renderer", "fsr2_quality_mode", system.config["fsr_quality"])
            yuzuConfig.set("Renderer", "fsr2_quality_mode\\default", "false")
        else:
            yuzuConfig.set("Renderer", "fsr2_quality_mode", "0")
            yuzuConfig.set("Renderer", "fsr2_quality_mode\\default", "true")

        # Anti aliasing method
        if system.isOptSet('aliasing_method'):
            yuzuConfig.set("Renderer", "anti_aliasing", system.config["aliasing_method"])
            yuzuConfig.set("Renderer", "anti_aliasing\\default", "false")
        else:
            yuzuConfig.set("Renderer", "anti_aliasing", "0")
            yuzuConfig.set("Renderer", "anti_aliasing\\default", "true")

        #ASTC Decoding Method
        if system.isOptSet('accelerate_astc'):
            yuzuConfig.set("Renderer", "accelerate_astc", system.config["accelerate_astc"])
            yuzuConfig.set("Renderer", "accelerate_astc\\default", "false")
        else:
            yuzuConfig.set("Renderer", "accelerate_astc", "1")
            yuzuConfig.set("Renderer", "accelerate_astc\\default", "true")

        # ASTC Texture Recompression
        if system.isOptSet('astc_recompression'):

            yuzuConfig.set("Renderer", "astc_recompression", system.config["astc_recompression"])
            yuzuConfig.set("Renderer", "astc_recompression\\default", "false")
            if system.config["astc_recompression"] == "0":
                yuzuConfig.set("Renderer", "use_vsync\\default", "true")
            yuzuConfig.set("Renderer", "async_astc", "false")
            yuzuConfig.set("Renderer", "async_astc\\default", "true")
        else:
            yuzuConfig.set("Renderer", "astc_recompression", "0")
            yuzuConfig.set("Renderer", "astc_recompression\\default", "true")
            yuzuConfig.set("Renderer", "async_astc", "false")
            yuzuConfig.set("Renderer", "async_astc\\default", "true")

    # Cpu Section
        if not yuzuConfig.has_section("Cpu"):
            yuzuConfig.add_section("Cpu")

        # Cpu Accuracy
        if system.isOptSet('cpuaccuracy'):
            yuzuConfig.set("Cpu", "cpu_accuracy", system.config["cpuaccuracy"])
            yuzuConfig.set("Cpu", "cpu_accuracy\\default", "false")
        else:
            yuzuConfig.set("Cpu", "cpu_accuracy", "0")
            yuzuConfig.set("Cpu", "cpu_accuracy\\default", "true")

    # System section
        if not yuzuConfig.has_section("System"):
            yuzuConfig.add_section("System")

        # Language
        if system.isOptSet('language'):
            yuzuConfig.set("System", "language_index", system.config["language"])
            yuzuConfig.set("System", "language_index\\default", "false")
        else:
            yuzuConfig.set("System", "language_index", "1")
            yuzuConfig.set("System", "language_index\\default", "true")

        # Audio Mode
        if system.isOptSet('audio_mode'):
            yuzuConfig.set("System", "sound_index", system.config["audio_mode"])
            yuzuConfig.set("System", "sound_index\\default", "false")
        else:
            yuzuConfig.set("System", "sound_index", "1")
            yuzuConfig.set("System", "sound_index\\default", "true")

        # Region
        if system.isOptSet('region'):
            yuzuConfig.set("System", "region_index", system.config["region"])
            yuzuConfig.set("System", "region_index\\default", "false")
        else:
            yuzuConfig.set("System", "region_index", "1")
            yuzuConfig.set("System", "region_index\\default", "true")

        # Dock Mode
        if system.isOptSet('dock_mode'):
            if system.config["dock_mode"] == "1":
                yuzuConfig.set("System", "use_docked_mode", "1")
                yuzuConfig.set("System", "use_docked_mode\\default", "true")
            elif system.config["dock_mode"] == "0":
                yuzuConfig.set("System", "use_docked_mode", "0")
                yuzuConfig.set("System", "use_docked_mode\\default", "false")
        else:
            yuzuConfig.set("System", "use_docked_mode", "1")
            yuzuConfig.set("System", "use_docked_mode\\default", "true")

        # controls section
        # Al inicio de writeYuzuConfig, antes de escribir nada en Controls:
        # controls section
        if not yuzuConfig.has_section("Controls"):
            yuzuConfig.add_section("Controls")
      
        eslog.warning("DEBUG: entrando bloque mandos, yuzu_auto=%s", system.config.get('yuzu_auto_controller_config'))
        if not system.isOptSet('yuzu_auto_controller_config') or system.config["yuzu_auto_controller_config"] != "0":
            # 1. Obtener los mapeos de hardware
            evdev_hidraw = evdev_to_hidraw()
            sdl_gamepads = list_sdl_gamepads(sdlversion)

            # 2. Inicializar TODOS los puertos posibles de Eden por defecto como desconectados
            # Esto evita que se queden mandos "fantasmas" de sesiones anteriores
            for slot in range(8):
                yuzuConfig.set("Controls", f"player_{slot}_connected", "false")
                yuzuConfig.set("Controls", f"player_{slot}_connected\\default", "false")

            guid_port = {}
            
            # 3. Iterar respetando el ID de jugador real asignado por Batocera
            for pad in playersControllers:
                # Batocera cuenta desde 1 (P1, P2, P3...), Eden cuenta desde 0 (player_0, player_1...)
                # Si pad.player no está disponible, hacemos fallback seguro al orden de la lista
                real_player_index = (pad.player - 1) if hasattr(pad, 'player') else playersControllers.index(pad)
                
                # Control de desbordamiento (Eden solo soporta hasta 8 mandos)
                if real_player_index < 0 or real_player_index > 7:
                    continue

                player_nb_str = f"player_{real_player_index}"

                # Resolver rutas de hardware para extraer inputs del gamepad
                hidraw_path = None
                if pad.device_path in evdev_hidraw:
                    hidraw_path = evdev_hidraw[pad.device_path]

                if hidraw_path and hidraw_path in sdl_gamepads:
                    pad.guid = sdl_gamepads[hidraw_path]['guid']
                    pad.inputs = sdl_gamepads[hidraw_path]['inputs']
                elif pad.device_path in sdl_gamepads:
                    pad.guid = sdl_gamepads[pad.device_path]['guid']
                    pad.inputs = sdl_gamepads[pad.device_path]['inputs']
                else:
                    for path, gamepad in sdl_gamepads.items():
                        if gamepad['guid'] == pad.guid:
                            pad.inputs = gamepad['inputs']
                            break

                # Control del índice del puerto físico por GUID duplicado
                if pad.guid not in guid_port:
                    guid_port[pad.guid] = 0
                else:
                    guid_port[pad.guid] = guid_port[pad.guid] + 1

                # Configurar tipo de mando basándonos en su índice real de Batocera
                yuzuConfig.set("Controls", player_nb_str + "_type\\default", "false")
                if system.isOptSet('p{}_pad'.format(real_player_index)):
                    yuzuConfig.set("Controls", player_nb_str + "_type", system.config["p{}_pad".format(real_player_index)])
                else:
                    yuzuConfig.set("Controls", player_nb_str + "_type", "0")

                # Tratamiento de botones invertidos de Nintendo
                if pad.real_name and "Nintendo" in pad.real_name:
                    yuzuButtonsMapping["button_a"] = "b"
                    yuzuButtonsMapping["button_b"] = "a"
                    yuzuButtonsMapping["button_x"] = "y"
                    yuzuButtonsMapping["button_y"] = "x"

                yuzu_inverse_button = system.config.get('yuzu_inverse_button', 'false').lower() == 'true'
                if yuzu_inverse_button:
                    yuzuButtonsMapping["button_a"] = "b"
                    yuzuButtonsMapping["button_b"] = "a"
                    yuzuButtonsMapping["button_x"] = "y"
                    yuzuButtonsMapping["button_y"] = "x"

                # Normalización del GUID para Eden
                eden_guid = pad.guid[:4] + "0000" + pad.guid[8:]

                # Inyectar mapeos específicos del jugador activo actual
                for x in yuzuButtonsMapping:
                    yuzuConfig.set("Controls", player_nb_str + "_" + x, '"{}"'.format(EdenGenerator.setButton(emulator, yuzuButtonsMapping[x], eden_guid, pad.inputs, guid_port[pad.guid])))
                for x in yuzuAxisMapping:
                    yuzuConfig.set("Controls", player_nb_str + "_" + x, '"{}"'.format(EdenGenerator.setAxis(yuzuAxisMapping[x], eden_guid, pad.inputs, guid_port[pad.guid])))

                # Configurar extras del jugador activo y MARCAR COMO CONECTADO
                yuzuConfig.set("Controls", player_nb_str + "_button_screenshot\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_button_screenshot", "[empty]")
                yuzuConfig.set("Controls", player_nb_str + "_motionleft\\default", "false")
                yuzuConfig.set("Controls", player_nb_str + "_motionleft", "[empty]")
                yuzuConfig.set("Controls", player_nb_str + "_motionright", "[empty]")
                yuzuConfig.set("Controls", player_nb_str + "_motionright\\default", "false")
                
                # ACTIVACIÓN EXPLÍCITA DEL MANDO CONECTADO
                yuzuConfig.set("Controls", player_nb_str + "_connected", "true")
                yuzuConfig.set("Controls", player_nb_str + "_connected\\default", "false")

                # Configuración de vibración
                if system.isOptSet('yuzu_rumble'):
                    yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled", system.config["yuzu_rumble"])
                    yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled\\default", "false")
                else:
                    yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled", "true")
                    yuzuConfig.set("Controls", player_nb_str + "_vibration_enabled\\default", "true")

    # telemetry section
        if not yuzuConfig.has_section("WebService"):
            yuzuConfig.add_section("WebService")
        yuzuConfig.set("WebService", "enable_telemetry", "false")
        yuzuConfig.set("WebService", "enable_telemetry\\default", "false")
        yuzuConfig.set("WebService", "enable_auto_update_check", "false")
        yuzuConfig.set("WebService", "enable_auto_update_check\\default", "false")

    # Services section
        if not yuzuConfig.has_section("Services"):
            yuzuConfig.add_section("Services")
        yuzuConfig.set("Services", "bcat_backend", "none")
        yuzuConfig.set("Services", "bcat_backend\\default", "none")

        ### update the configuration file
        if not os.path.exists(os.path.dirname(yuzuConfigFile)):
            os.makedirs(os.path.dirname(yuzuConfigFile))

        with open(yuzuConfigFile, 'w') as configfile:
            yuzuConfig.write(configfile)
    
    @staticmethod
    def setButton(emulator, key, padGuid, padInputs, port):
        if key in padInputs:
            input_data = padInputs[key]
            print(f"HAT: id={input_data.id}, value={input_data.value}", file=sys.stderr)
            if input_data.type == "button":
                return f"engine:sdl,port:{port},guid:{padGuid},button:{input_data.id}"
            elif input_data.type == "hat":
                direction = EdenGenerator.hatdirectionvalue(input_data.value)
                return f"engine:sdl,guid:{padGuid},port:{port},pad:0,hat:{input_data.id},direction:{direction}"
            elif input_data.type == "axis":
                return f"engine:sdl,port:{port},guid:{padGuid},axis:{input_data.id},threshold:0.500000,invert:+"
        return "[empty]"

    
    @staticmethod
    def hatdirectionvalue(value):
        try:
            val = int(value)
            mapping = {1: "up", 4: "down", 2: "right", 8: "left"}
            return mapping.get(val, "unknown")
        except:
            return "unknown"
        
    @staticmethod
    def setAxis(key, padGuid, padInputs, port):
        inputx = "0"
        inputy = "0"

        left_key = "joystick1left" if key == "joystick1" else "joystick2left"
        up_key = "joystick1up" if key == "joystick1" else "joystick2up"

        if left_key in padInputs and padInputs[left_key].id is not None:
            inputx = padInputs[left_key].id
        if up_key in padInputs and padInputs[up_key].id is not None:
            inputy = padInputs[up_key].id

        return f"engine:sdl,port:{port},guid:{padGuid},axis_x:{inputx},axis_y:{inputy},offset_x:-0.000000,offset_y:0.000000,invert_x:+,invert_y:+,deadzone:0.150000"
        
    def getMouseMode(self, config, rom):
        return True