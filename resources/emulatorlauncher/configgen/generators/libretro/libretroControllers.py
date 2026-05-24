from __future__ import annotations

from glob import glob
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from configgen.controller import getJoystickHardwareIds
from configgen.generators.libretro.libretroPaths import RETROARCH_CONFIG

from ...controllersConfig import getAssociatedMouse, getDevicesInformation

if TYPE_CHECKING:

    from ...controller import Controller, Controllers
    from ...Emulator import Emulator
    from ...input import Input
    from ...settings.unixSettings import UnixSettings


# Map an emulationstation direction to the corresponding retroarch
retroarchdirs = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'}

# Map an emulationstation joystick to the corresponding retroarch
retroarchjoysticks = {'joystick1up': 'l_y', 'joystick1left': 'l_x', 'joystick2up': 'r_y', 'joystick2left': 'r_x'}

# Map an emulationstation input type to the corresponding retroarch type
typetoname = {'button': 'btn', 'hat': 'btn', 'axis': 'axis', 'key': 'key'}

# Map an emulationstation input hat to the corresponding retroarch hat value
hatstoname = {'1': 'up', '2': 'right', '4': 'down', '8': 'left'}

# Write a configuration for a specified controller
# Warning, function used by amiberry because it reads the same retroarch formatting
def writeControllersConfig(
    retroconfig: UnixSettings,
    system: Emulator,
    controllers: Controllers,
    lightgun: bool,
    /,
) -> None:

    cleanControllerConfig(retroconfig, controllers)

    # hotkeys, forced to match with the hotkeys system
    retroconfig.save('input_enable_hotkey',       '"shift"')
    retroconfig.save('input_menu_toggle',         '"f1"')
    retroconfig.save('input_fps_toggle',          '"f2"')
    retroconfig.save('input_exit_emulator',       '"escape"')
    retroconfig.save('input_pause_toggle',        '"p"')
    retroconfig.save('input_save_state',          '"f3"')
    retroconfig.save('input_load_state',          '"f4"')
    retroconfig.save('input_state_slot_decrease', '"f5"')
    retroconfig.save('input_state_slot_increase', '"f6"')
    retroconfig.save('input_ai_service',          '"f9"')
    retroconfig.save('input_reset',               '"f10"')
    retroconfig.save('input_rewind',              '"f11"')

    # See if FF is toggle or hold
    ff_action = 'toggle_fast_forward' if (
        system.isOptSet('toggle_fast_forward')
        and system.getOptBoolean('toggle_fast_forward')
    ) else 'hold_fast_forward'

    retroconfig.save(f'input_{ff_action}',        '"f12"')
    retroconfig.save('input_screenshot',          '"nul"')
    retroconfig.save('input_audio_mute',          '"nul"')
    retroconfig.save('input_grab_mouse_toggle',   '"nul"')

    # --- MAPEO ÚNICO RESILIENTE PARA EL DRIVER UDEV ---
    udev_index_map = {}
    try:
        import glob
        import os

        # Listamos y ordenamos numéricamente los eventX una sola vez
        event_devices = glob.glob('/dev/input/event*')
        event_devices.sort(key=lambda x: int(x.split('event')[-1]))

        # Resolvemos las rutas reales de los mandos del sistema que existen físicamente
        valid_system_paths = []
        for c in controllers:
            if c.device_path and os.path.exists(c.device_path):
                valid_system_paths.append(os.path.realpath(c.device_path))

        # Ordenamos los mandos según su aparición en los nodos del kernel
        valid_system_paths.sort(key=lambda x: event_devices.index(x) if x in event_devices else 999)

        # Poblamos un diccionario indexando por su ruta real desreferenciada
        for index, path in enumerate(valid_system_paths):
            udev_index_map[path] = str(index)
    except Exception:
        # Si falla la lectura de I/O, el diccionario se queda vacío y aplicará fallback
        pass
    # --------------------------------------------------

    for controller in controllers:
        mouseIndex: str | None = None
        if system.name in ['nds', '3ds']:
            deviceList = getDevicesInformation()
            mouseIndex = getAssociatedMouse(deviceList, controller.device_path)
        if mouseIndex is None:
            mouseIndex = '0'
            
        # Determinamos el joypad_index usando el mapa calculado o fallback del frontend
        current_real_path = os.path.realpath(controller.device_path) if controller.device_path else ""
        joypad_index = udev_index_map.get(current_real_path, controller.index)

        # Pasamos directamente el índice resuelto a la función hija
        writeControllerConfig(retroconfig, controller, controller.player_number, system, joypad_index, lightgun, mouseIndex)    

# Remove all controller configurations
def cleanControllerConfig(retroconfig: UnixSettings, controllers: Controllers, /) -> None:
    retroconfig.disable_all('input_player')

    for x in [
            'state_slot_increase',  'load_state',        'save_state',
            'state_slot_decrease',  'reset',             'exit_emulator',
            'rewind',               'hold_fast_forward', 'toggle_fast_forward',
            'screenshot',           'disk_prev',         'disk_next',
            'disk_eject_toggle',    'shader_prev',       'shader_next',
            'ai_service',           'menu_toggle'
    ]:
        retroconfig.disable_all(f'input_{x}')

# Write the hotkey for player 1
def _hotkey_save(key: str, input_obj: Input, config: dict[str, object] | None = None, /) -> tuple[str, str]:
    """Devuelve la tupla (clave, valor) con el sufijo correcto buscando en el Plan B o en el objeto Input."""
    
    # RAMA PLAN B: Buscamos en las claves que el parseador del archivo ya inyectó en config
    if config is not None:
        # Traducimos el nombre genérico de ES (pagedown/pageup) al botón real de RetroArch (r/l)
        ra_btn = 'r' if input_obj == 'pagedown' else ('l' if input_obj == 'pageup' else input_obj)
        
        btn_key = f"input_player1_{ra_btn.name}_btn"
        axis_key = f"input_player1_{ra_btn.name}_axis"
        
        if btn_key in config:
            return f"{key}_btn", str(config[btn_key])
        elif axis_key in config:
            return f"{key}_axis", str(config[axis_key])
            
        # Fallback de seguridad: Si por lo que sea no se indexó, devolvemos tupla vacía para no romper
        return "", ""

    # RAMA PLAN A: Mapeo tradicional por EmulationStation
    value = getConfigValue(input_obj)
    suffix = '_axis' if input_obj.type == 'axis' else '_btn'
    return f'{key}{suffix}', value

def writeHotKeyConfig(controller: Controller, manual_config: bool, config: dict[str, object] | None = None, /) -> dict[str, str]:
    """Genera el diccionario de hotkeys desde EmulationStation sin romper bucles."""
    hotkeys = {}
    if not controller:
        return hotkeys
    
    pad = controller.inputs
    chosen_hotkey = pad.get('hotkey') or pad.get('select')
    if not chosen_hotkey or chosen_hotkey.type != 'button':
        return hotkeys

    if not manual_config:
        hotkeys['input_enable_hotkey_btn'] = getConfigValue(chosen_hotkey)

    hotkey_map = {
        'start':    'input_exit_emulator',
        'b':        'input_menu_toggle',
        'x':        'input_screenshot',
        'a':        'input_reset',
        'r2':       'input_save_state',
        'l2':       'input_load_state',
        'right':    'input_hold_fast_forward',
        'left':     'input_rewind',
        'up':       'input_disk_eject_toggle',
        'pagedown': 'input_disk_next',
        'pageup':   'input_disk_prev',
    }

    for btn, rakey in hotkey_map.items():
        if btn in pad:
            k, v = _hotkey_save(rakey, pad[btn], config)
            # Transformamos 'input_exit_emulator_btn' en 'input_player1_exit_emulator_btn'
            # Cortamos a partir del carácter 6 ('input_') y le metemos el prefijo del player 1
            hotkeys[k] = v
            
    return hotkeys            

# Write a configuration for a specified controller
def writeControllerConfig(
    retroconfig: UnixSettings,
    controller: Controller,
    playerIndex: int,
    system: Emulator,
    joypad_index: str,
    lightgun: bool,
    mouseIndex: str,
    /,
):
    generatedConfig = generateControllerConfig(controller, system, lightgun, mouseIndex)
    print(f"[DEBUG5] escribiendo {len(generatedConfig)} claves para player{playerIndex} ({controller.real_name})")
    print(f"[DEBUG5] joypad_index para retroarch/udev: {joypad_index}")
    for key in generatedConfig:
        retroconfig.save(key, generatedConfig[key])

    retroconfig.save(f'input_player{playerIndex}_joypad_index', str(joypad_index))
    retroconfig.save(f'input_player{playerIndex}_analog_dpad_mode', getAnalogMode(controller, system))
    
# Create a configuration for a given controller
def generateControllerConfig(
    controller: Controller,
    system: Emulator,
    lightgun: bool,
    mouseIndex: str,
    /,
) -> dict[str, object]:

    config: dict[str, object] = {}
    hw_ids = getJoystickHardwareIds(controller.device_path)
    
    if hw_ids:
        vendor_dec, product_dec = hw_ids
        
        hw_cfg_name = f"{vendor_dec}-{product_dec}.cfg"
        hw_cfg_path = RETROARCH_CONFIG / 'autoconfig' / hw_cfg_name
        
        if hw_cfg_path.exists():
            p_num = controller.player_number
            print(f"[DEBUG_HW] Aplicando perfil {hw_cfg_name} al Player {p_num}")
            
            cfg_hotkey = None
            cfg_select = None
            
            try:
                with open(hw_cfg_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith(('#', ';')):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k, v = k.strip(), v.strip()
                            
                            if k in ('input_driver', 'input_device', 'input_device_display_name', 'input_vendor_id', 'input_product_id'):
                                continue

                            if k.startswith('input_'):
                                # Capturamos los valores limpios que usaremos para la hotkey de respaldo
                                if k == 'input_enable_hotkey_btn':
                                    cfg_hotkey = v
                                elif k == 'input_select_btn':
                                    cfg_select = v
                                
                                suffix = k[6:]
                                config[f"input_player{p_num}_{suffix}"] = v        
                
                # Al salir del archivo, si eres Player 1, metemos la hotkey global de tu .cfg
                if p_num == 1:
                    config['input_enable_hotkey_btn'] = cfg_hotkey or cfg_select
                    config.update(writeHotKeyConfig(controller, True, config))

                if not lightgun:
                    config[f'input_player{p_num}_mouse_index'] = mouseIndex
                    
                return config
                
            except Exception as e:
                print(f"[DEBUG_HW] Falló la lectura del perfil {hw_cfg_name}: {e}") 
    # Si no detectamos mapping manual de mando, seguimos
    # Map an emulationstation button name to the corresponding retroarch name
    retroarchbtns = {'a': 'a', 'b': 'b', 'x': 'x', 'y': 'y', \
                     'pageup': 'l', 'pagedown': 'r', 'l2': 'l2', 'r2': 'r2', \
                     'l3': 'l3', 'r3': 'r3', \
                     'start': 'start', 'select': 'select'}

    # X Y L1 L2  ---> X Y R1 L1
    # A B R1 R2  ---> A B R2 L2
    if system.config.get('altlayout') == 'fightstick':
        retroarchbtns['pageup'] = 'l2'
        retroarchbtns['pagedown'] = 'l'
        retroarchbtns['l2'] = 'r2'
        retroarchbtns['r2'] = 'r'

    retroarchGunbtns = {'a': 'aux_a', 'b': 'aux_b', 'y': 'aux_c', \
                        'pageup': 'offscreen_shot', 'pagedown': 'trigger', \
                        'start': 'start', 'select': 'select'}

    # Some input adaptations for some cores...
    # Z is important, in case l2 (z) is not available for this pad, use l1
    if system.name == "n64" and 'r2' not in controller.inputs:
        retroarchbtns["pageup"] = "l2"
        retroarchbtns["l2"] = "l"

    if system.name == "dreamcast" and system.config.core == "flycast" and 'r2' not in controller.inputs:
        retroarchbtns["pageup"] = "l2"
        retroarchbtns["l2"] = "l"
        retroarchbtns["pagedown"] = "r2"
        retroarchbtns["r2"] = "r"

    # Fix for reversed inputs in Yabasanshiro core which is unmaintained by retroarch
    if system.config.core == 'yabasanshiro':
        retroarchbtns["pageup"] = "r"
        retroarchbtns["pagedown"] = "l"

    # config['input_device'] = '"%s"' % controller.real_name
    for btnkey in retroarchbtns:
        btnvalue = retroarchbtns[btnkey]
        if btnkey in controller.inputs:
            input = controller.inputs[btnkey]
            config[f'input_player{controller.player_number}_{btnvalue}_{typetoname[input.type]}'] = getConfigValue(
                input)
    if lightgun:
        for btnkey in retroarchGunbtns: # Gun Mapping
            btnvalue = retroarchGunbtns[btnkey]
            if btnkey in controller.inputs:
                input = controller.inputs[btnkey]
                config[f'input_player{controller.player_number}_gun_{btnvalue}_{typetoname[input.type]}'] = getConfigValue(
                    input)
    for dirkey in retroarchdirs:
        dirvalue = retroarchdirs[dirkey]
        if dirkey in controller.inputs:
            input = controller.inputs[dirkey]
            config[f'input_player{controller.player_number}_{dirvalue}_{typetoname[input.type]}'] = getConfigValue(
                input)
            if lightgun:
                # Gun Mapping
                config[f'input_player{controller.player_number}_gun_dpad_{dirvalue}_{typetoname[input.type]}'] = getConfigValue(
                    input)
    for jskey in retroarchjoysticks:
        jsvalue = retroarchjoysticks[jskey]
        if jskey in controller.inputs:
            input = controller.inputs[jskey]
            if input.value == '-1':
                config[f'input_player{controller.player_number}_{jsvalue}_minus_axis'] = f'-{input.id}'
                config[f'input_player{controller.player_number}_{jsvalue}_plus_axis'] = f'+{input.id}'
            else:
                config[f'input_player{controller.player_number}_{jsvalue}_minus_axis'] = f'+{input.id}'
                config[f'input_player{controller.player_number}_{jsvalue}_plus_axis'] = f'-{input.id}'

    if not lightgun:
        config[f'input_player{controller.player_number}_mouse_index'] = mouseIndex
    
    # Si entra por aquí (Plan A), mete las hotkeys de EmulationStation
    if controller.player_number == 1:
        config.update(writeHotKeyConfig(controller, False))
        
    return config

# Returns the value to write in retroarch config file, depending on the type
def getConfigValue(input: Input, /) -> str | None:
    if input.type == 'button':
        return f'"{input.id}"'          # <--- Forzamos las comillas aquí
    if input.type == 'axis':
        if input.value == '-1':
            return f'"-{input.id}"'     # <--- Forzamos las comillas aquí
        return f'"+{input.id}"'         # <--- Forzamos las comillas aquí
    if input.type == 'hat':
        return f'"h{input.id}{hatstoname[input.value]}"' # <--- Forzamos las comillas aquí
    if input.type == 'key':
        return f'"{input.id}"'          # <--- Forzamos las comillas aquí
    return None

# Return the retroarch analog_dpad_mode
def getAnalogMode(controller: Controller, system: Emulator, /) -> Literal['0', '1']:
    # don't enable analog as hat mode for some systems
    if system.name == 'n64' or system.name == 'dreamcast' or system.name == '3ds':
        return '0'

    for dirkey in retroarchdirs:
        if dirkey in controller.inputs and (controller.inputs[dirkey].type == 'button' or controller.inputs[dirkey].type == 'hat'):
            return '1'
    return '0'
