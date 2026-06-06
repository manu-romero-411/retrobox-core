#!/usr/bin/env python3
"""
gamepad-mapper.py — Traduce combinaciones de botones del mando a eventos del sistema.

Lee el mando via pygame/SDL2, que usa los mismos button IDs que EmulationStation,
y emite los eventos de teclado/ratón via evdev UInput.

Dependencias:
    pip install pygame evdev

Permisos (una sola vez):
    sudo usermod -aG input $USER   # luego cerrar sesión y volver a entrar

Uso:
    python3 gamepad-mapper.py --list
    python3 gamepad-mapper.py \\
        --guid 050000007e0500000920000001800000 \\
        --sdl_id 0 \\
        --es-input ~/.emulationstation/es_input.cfg \\
        [--profile hotkeys.json] [--debug]

Formato del perfil JSON:
    {
      "cooldown": 0.5,
      "mappings": [
        {
          "buttons": ["hotkey", "start"],
          "action": { "type": "key", "keys": ["KEY_LEFTALT", "KEY_F4"] }
        },
        {
          "buttons": ["hotkey", "r3"],
          "action": { "type": "click", "button": "BTN_LEFT" }
        },
        {
          "buttons": ["joystick2left", "joystick2up"],
          "action": { "type": "mouse", "speed": 800, "deadzone": 0.15, "acceleration": 1.5 },
          "condition": ["hotkey"]
        }
      ]
    }

    Tipos de acción:
        key    → { "type": "key",   "keys": ["KEY_X", ...] }
        click  → { "type": "click", "button": "BTN_LEFT" }
        mouse  → { "type": "mouse", "speed": float, "deadzone": float, "acceleration": float }
                 Requiere exactamente 2 nombres ES que sean ejes (joystick*left/up).

    Campos opcionales en cada mapping:
        "condition"  → lista de nombres ES que deben estar pulsados adicionalmente
        "_disabled"  → true para ignorar la entrada sin borrarla
        "_comment"   → texto libre ignorado por el parser
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
_logger = logging.getLogger(__name__)

try:
    import pygame
    import pygame.joystick
except ImportError:
    _logger.error("Falta pygame.\n  pip install pygame")
    sys.exit(1)

try:
    from evdev import ecodes as ec, UInput
except ImportError:
    _logger.error("Falta evdev.\n  pip install evdev")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
#  RESOLUCIÓN DE NOMBRES DE ECODES
# ══════════════════════════════════════════════════════════════════════

def _resolve_ecode(name: str) -> int:
    """Convierte un nombre de ecodes ('KEY_F4', 'BTN_LEFT', …) a su valor entero."""
    v = getattr(ec, name, None)
    if v is None:
        raise ValueError(
            f"Nombre de ecodes desconocido: '{name}'. "
            f"Consulta `python3 -c \"from evdev import ecodes; help(ecodes)\"`"
        )
    return int(v)


# ══════════════════════════════════════════════════════════════════════
#  ACCIONES PUNTUALES
# ══════════════════════════════════════════════════════════════════════

@dataclass
class KeyAction:
    """Pulsa y suelta una secuencia de teclas."""
    keys: list[int]

    def press_down(self, ui: "UInputPair"):
        for k in self.keys:
            ui.write_key(k, 1)
        ui.syn(has_kbd=True)

    def press_up(self, ui: "UInputPair"):
        for k in reversed(self.keys):
            ui.write_key(k, 0)
        ui.syn(has_kbd=True)

    def uinput_keys(self) -> set[int]:
        return set(self.keys)

    def uinput_rel(self) -> set[int]:
        return set()


@dataclass
class ClickAction:
    """Botón de ratón mantenido mientras el botón del mando esté pulsado."""
    button: int = ec.BTN_LEFT

    def press_down(self, ui: "UInputPair"):
        ui.write_key(self.button, 1)
        ui.syn(has_mouse=True)

    def press_up(self, ui: "UInputPair"):
        ui.write_key(self.button, 0)
        ui.syn(has_mouse=True)

    def uinput_keys(self) -> set[int]:
        return {self.button}

    def uinput_rel(self) -> set[int]:
        return set()


@dataclass
class CallbackAction:
    """Acción arbitraria en Python (solo disponible vía código, no desde JSON)."""
    fn: Callable[[], None]

    def press_down(self, ui: "UInputPair"):
        self.fn()

    def press_up(self, ui: "UInputPair"):
        pass  # callbacks no tienen fase de release

    def uinput_keys(self) -> set[int]:
        return set()

    def uinput_rel(self) -> set[int]:
        return set()


# ══════════════════════════════════════════════════════════════════════
#  ACCIÓN CONTINUA (movimiento de ratón)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class AxisMouseConfig:
    """
    Mapea un par de ejes analógicos SDL al movimiento continuo del ratón.

    axis_x / axis_y  son nombres ES (p.ej. "joystick2left", "joystick2up").
    condition        lista de nombres ES que deben estar pulsados (None = siempre activo).
    """
    axis_x:       str
    axis_y:       str
    speed:        float = 800.0
    deadzone:     float = 0.15
    acceleration: float = 1.5
    condition:    tuple[str, ...] | None = None


# ══════════════════════════════════════════════════════════════════════
#  PARSER DE PERFILES JSON
# ══════════════════════════════════════════════════════════════════════

# Tipos de retorno de load_profile
AbstractHotkeys = dict[tuple[str, ...], KeyAction | ClickAction | CallbackAction]
AxisMouseList   = list[AxisMouseConfig]

# Nombres de stick completo → (eje_x, eje_y)
_STICK_AXES = {
    "joystick1": ("joystick1left", "joystick1up"),
    "joystick2": ("joystick2left", "joystick2up"),
}

def load_profile(path: str, player: int = 1) -> tuple[AbstractHotkeys, AxisMouseList, float]:
    """
    Carga un perfil en formato evmapy nativo y devuelve:
        (hotkeys_abstractos, lista_axis_mouse, cooldown)

    Formato esperado (compatible con Batocera evmapy):
    {
      "cooldown": 0.5,           ← opcional, por defecto 0.5 s
      "actions_player1": [
        {
          "trigger": "joystick2",         ← stick completo → ratón
          "type": "mouse",
          "speed": 800, "deadzone": 0.15, "acceleration": 1.5,  ← opcionales
          "condition": "hotkey"           ← opcional
        },
        {
          "trigger": ["hotkey", "start"], ← combo
          "type": "key",
          "target": ["KEY_LEFTALT", "KEY_F4"]
        },
        {
          "trigger": "r3",
          "type": "key",
          "target": "BTN_LEFT"           ← BTN_* también se acepta en type:key
        }
      ]
    }

    Reglas:
    - "trigger" puede ser string o lista de strings (nombres ES).
    - "target"  puede ser string o lista de strings (nombres evdev).
    - type "mouse": "trigger" debe ser un nombre de stick completo
      ("joystick1" / "joystick2") o exactamente dos nombres de eje
      ("joystick2left" + "joystick2up"). Se expande internamente.
    - "condition" (string o lista) se suma al combo en hotkeys,
      o se usa como condición de activación en mouse.
    - Entradas sin "trigger" o sin "type" se ignoran con warning.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    cooldown: float = float(data.get("cooldown", 0.5))
    hotkeys:         AbstractHotkeys              = {}
    axis_mouse:      AxisMouseList                = []
    combo_cooldowns: dict[tuple[str,...], float]  = {}

    # Buscar la lista de acciones para el jugador indicado.
    # Prioridad: actions_playerN → mappings (fallback genérico)
    player_key = f"actions_player{player}"
    entries = data.get(player_key) or data.get("mappings") or []
    if not entries:
        available = [k for k in data if k.startswith("actions_")]
        _logger.warning(
            f"No se encontró '{player_key}' en el perfil. "
            f"Secciones disponibles: {available or ['(ninguna)'] }"
        )

    for i, entry in enumerate(entries):
        atype = entry.get("type", "")
        if not atype:
            _logger.warning(f"  Mapping #{i}: falta 'type' → ignorado.")
            continue

        raw_trigger = entry.get("trigger")
        if raw_trigger is None:
            _logger.warning(f"  Mapping #{i}: falta 'trigger' → ignorado.")
            continue

        # Normalizar trigger a lista
        triggers: list[str] = (
            raw_trigger if isinstance(raw_trigger, list) else [raw_trigger]
        )

        # Normalizar condition a lista (puede ser string, lista o ausente)
        raw_cond = entry.get("condition")
        condition: list[str] = (
            raw_cond if isinstance(raw_cond, list)
            else [raw_cond] if raw_cond
            else []
        )

        # ── Acción de ratón ──────────────────────────────────────────
        if atype == "mouse":
            # Expandir "joystick2" → ("joystick2left", "joystick2up")
            if len(triggers) == 1 and triggers[0] in _STICK_AXES:
                axis_x, axis_y = _STICK_AXES[triggers[0]]
            elif len(triggers) == 2:
                axis_x, axis_y = triggers[0], triggers[1]
            else:
                _logger.warning(
                    f"  Mapping #{i}: type 'mouse' necesita un nombre de stick "
                    f"('joystick1'/'joystick2') o exactamente 2 ejes → ignorado."
                )
                continue

            cfg = AxisMouseConfig(
                axis_x       = axis_x,
                axis_y       = axis_y,
                speed        = float(entry.get("speed",        800.0)),
                deadzone     = float(entry.get("deadzone",     0.15)),
                acceleration = float(entry.get("acceleration", 1.5)),
                condition    = tuple(condition) if condition else None,
            )
            axis_mouse.append(cfg)
            cond_str = " + ".join(condition) if condition else "siempre"
            _logger.debug(
                f"  Mapping #{i}: mouse ({axis_x}, {axis_y})  "
                f"speed={cfg.speed}  dz={cfg.deadzone}  "
                f"accel={cfg.acceleration}  condición={cond_str}"
            )

        # ── Acción puntual (key / BTN_*) ─────────────────────────────
        elif atype == "key":
            raw_target = entry.get("target")
            if raw_target is None:
                _logger.warning(f"  Mapping #{i}: type 'key' sin 'target' → ignorado.")
                continue
            targets: list[str] = (
                raw_target if isinstance(raw_target, list) else [raw_target]
            )
            try:
                codes = [_resolve_ecode(t) for t in targets]
            except ValueError as ex:
                _logger.warning(f"  Mapping #{i}: {ex} → ignorado.")
                continue

            # BTN_* único → ClickAction; cualquier otra cosa → KeyAction
            if len(codes) == 1 and targets[0].startswith("BTN_"):
                action: KeyAction | ClickAction = ClickAction(codes[0])
            else:
                action = KeyAction(codes)

            # Combo = triggers + condition
            combo = tuple(triggers + condition)
            if combo in hotkeys:
                _logger.warning(
                    f"  Mapping #{i}: combo {combo!r} duplicado → reemplazado."
                )
            hotkeys[combo] = action  # type: ignore[assignment]

            # Cooldown por entrada:
            #   - Explícito en el JSON ("cooldown": N) → ese valor.
            #   - Botón único sin hotkey → 0 s (permite clics rápidos).
            #   - Combo multi-botón     → cooldown global (evita doble disparo).
            if "cooldown" in entry:
                combo_cooldowns[combo] = float(entry["cooldown"])
            elif len(combo) == 1:
                combo_cooldowns[combo] = 0.0
            else:
                combo_cooldowns[combo] = cooldown

            _logger.debug(
                f"  Mapping #{i}: {' + '.join(combo)}  →  {action}  "
                f"(cd={combo_cooldowns[combo]}s)"
            )

        else:
            _logger.warning(f"  Mapping #{i}: tipo '{atype}' desconocido → ignorado.")

    _logger.info(
        f"Perfil '{path}' cargado: "
        f"{len(hotkeys)} hotkey(s), "
        f"{len(axis_mouse)} eje(s) de ratón, "
        f"cooldown global={cooldown}s"
    )
    return hotkeys, axis_mouse, combo_cooldowns


# ══════════════════════════════════════════════════════════════════════
#  INPUTS ABSTRACTOS
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ButtonInput:
    sdl_id: int

@dataclass(frozen=True)
class HatInput:
    hat_id: int
    direction: int      # máscara ES: 1=up 2=right 4=down 8=left

@dataclass(frozen=True)
class AxisInput:
    axis_id: int
    value: int          # -1 o +1: lado activo del eje en es_input


# ══════════════════════════════════════════════════════════════════════
#  CÓDIGOS VIRTUALES INTERNOS
# ══════════════════════════════════════════════════════════════════════

BTN_VIRTUAL_BASE  = 0x0000
HAT_VIRTUAL_BASE  = 0x1000
AXIS_VIRTUAL_BASE = 0x2000
AXIS_THRESHOLD    = 0.5

_HAT_DIR_BIT = {1: 0, 2: 1, 4: 2, 8: 3}

def _btn_code(sdl_id: int) -> int:
    return BTN_VIRTUAL_BASE + sdl_id

def _hat_code(hat_id: int, direction: int) -> int:
    return HAT_VIRTUAL_BASE + hat_id * 4 + _HAT_DIR_BIT[direction]

def _axis_code(axis_id: int, positive: bool) -> int:
    return AXIS_VIRTUAL_BASE + axis_id * 2 + (1 if positive else 0)

def input_to_virtual(inp: ButtonInput | HatInput | AxisInput) -> int:
    if isinstance(inp, ButtonInput):
        return _btn_code(inp.sdl_id)
    if isinstance(inp, HatInput):
        return _hat_code(inp.hat_id, inp.direction)
    if isinstance(inp, AxisInput):
        return _axis_code(inp.axis_id, inp.value > 0)
    raise TypeError(f"Tipo desconocido: {type(inp)}")


# ══════════════════════════════════════════════════════════════════════
#  PARSER DE es_input.cfg
# ══════════════════════════════════════════════════════════════════════

ESInputMap = dict[str, ButtonInput | HatInput | AxisInput]

def _guid_vendor_product(guid: str) -> tuple[int, int]:
    import struct
    b = bytes.fromhex(guid.lower().replace("-", ""))
    return struct.unpack_from("<H", b, 4)[0], struct.unpack_from("<H", b, 8)[0]

def _guid_matches(a: str, b: str) -> bool:
    a, b = a.lower().replace("-",""), b.lower().replace("-","")
    return a == b or _guid_vendor_product(a) == _guid_vendor_product(b)

def parse_es_input(xml_path: str, guid: str) -> ESInputMap:
    """
    Busca la configuración del mando en es_input.cfg.
    Aplica una búsqueda en dos pasadas: primero por GUID exacto para evitar 
    conflictos con mandos virtuales, y luego por Vendor/Product como fallback.
    """
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        _logger.error(f"Error al parsear el archivo XML {xml_path}: {e}")
        raise

    cfg = None
    target_guid = guid.lower().replace("-", "")

    # Primera pasada: Coincidencia estricta (GUID exacto de 32 caracteres)
    for ic in root.findall("inputConfig"):
        if ic.get("type") == "joystick":
            es_guid = ic.get("deviceGUID", "").lower().replace("-", "")
            if es_guid == target_guid:
                cfg = ic
                _logger.debug(f"Mando encontrado por GUID exacto: '{ic.get('deviceName')}'")
                break

    # Segunda pasada: Coincidencia difusa (Vendor/Product) priorizando mandos reales (no virtuales)
    if cfg is None:
        for ic in root.findall("inputConfig"):
            if ic.get("type") == "joystick" and _guid_matches(guid, ic.get("deviceGUID", "")):
                if "virtual" not in ic.get("deviceName", "").lower():
                    cfg = ic
                    _logger.debug(f"Mando encontrado por coincidencia difusa (físico): '{ic.get('deviceName')}'")
                    break
        
        # Fallback difuso total si solo existen configuraciones virtuales
        if cfg is None:
            for ic in root.findall("inputConfig"):
                if ic.get("type") == "joystick" and _guid_matches(guid, ic.get("deviceGUID", "")):
                    cfg = ic
                    _logger.debug(f"Mando encontrado por coincidencia difusa total: '{ic.get('deviceName')}'")
                    break

    if cfg is None:
        raise KeyError(f"No se encontró ninguna configuración compatible para el GUID {guid} en {xml_path}")

    _logger.debug(f"Cargando mapa de entradas desde ES input: {cfg.get('deviceName')} ({len(cfg.findall('input'))} entradas)")

    result: ESInputMap = {}
    for inp in cfg.findall("input"):
        name, itype = inp.get("name"), inp.get("type")
        iid, ivalue = int(inp.get("id", 0)), int(inp.get("value", 1))
        if itype == "button":
            result[name] = ButtonInput(sdl_id=iid)
        elif itype == "hat":
            result[name] = HatInput(hat_id=iid, direction=ivalue)
        elif itype == "axis":
            result[name] = AxisInput(axis_id=iid, value=ivalue)

    return result


# ══════════════════════════════════════════════════════════════════════
#  RESOLUCIÓN DE HOTKEYS Y AXIS MOUSE
# ══════════════════════════════════════════════════════════════════════

ResolvedHotkeys = dict[frozenset[int], KeyAction | ClickAction | CallbackAction]

CooldownMap = dict[frozenset[int], float]

def resolve_hotkeys(
    abstract:        AbstractHotkeys,
    es_map:          ESInputMap,
    combo_cooldowns: dict[tuple[str,...], float] | None = None,
) -> tuple[ResolvedHotkeys, CooldownMap]:
    resolved:  ResolvedHotkeys = {}
    cd_map:    CooldownMap     = {}
    for names, action in abstract.items():
        missing = [n for n in names if n not in es_map]
        if missing:
            _logger.warning(f"Hotkey {names!r}: {missing!r} no está en el mando ES — ignorada.")
            continue
            
        code_set = frozenset(input_to_virtual(es_map[n]) for n in names)
        
        # Bloque de mitigación: Evitar el colapso físico de teclas lógicas
        if len(code_set) < len(names):
            _logger.debug(f"Combo ignorado {names!r}: solapamiento físico en el hardware.")
            continue
            
        resolved[code_set] = action
        if combo_cooldowns and names in combo_cooldowns:
            cd_map[code_set] = combo_cooldowns[names]
        _logger.debug(f"  {' + '.join(names)}  →  {' + '.join(hex(c) for c in sorted(code_set))}")
    return resolved, cd_map


@dataclass
class ResolvedAxisMouse:
    axis_id_x:    int
    axis_sign_x:  int
    axis_id_y:    int
    axis_sign_y:  int
    speed:        float
    deadzone:     float
    acceleration: float
    condition:    frozenset[int] | None


def resolve_axis_mouse(configs: list[AxisMouseConfig], es_map: ESInputMap) -> list[ResolvedAxisMouse]:
    result = []
    for cfg in configs:
        missing = [n for n in (cfg.axis_x, cfg.axis_y) if n not in es_map]
        if missing:
            _logger.warning(f"AxisMouse: {missing!r} no está en el mapa ES — ignorado.")
            continue
        inp_x = es_map[cfg.axis_x]
        inp_y = es_map[cfg.axis_y]
        if not isinstance(inp_x, AxisInput) or not isinstance(inp_y, AxisInput):
            _logger.warning(f"AxisMouse: '{cfg.axis_x}'/'{cfg.axis_y}' deben ser ejes, no botones.")
            continue

        cond = None
        if cfg.condition:
            missing_c = [n for n in cfg.condition if n not in es_map]
            if missing_c:
                _logger.warning(f"AxisMouse condición: {missing_c!r} no en mapa ES — ignorada.")
                continue
            cond = frozenset(input_to_virtual(es_map[n]) for n in cfg.condition)

        result.append(ResolvedAxisMouse(
            axis_id_x   = inp_x.axis_id,
            axis_sign_x = inp_x.value,
            axis_id_y   = inp_y.axis_id,
            axis_sign_y = inp_y.value,
            speed       = cfg.speed,
            deadzone    = cfg.deadzone,
            acceleration= cfg.acceleration,
            condition   = cond,
        ))
        cond_str = " + ".join(cfg.condition) if cfg.condition else "siempre"
        _logger.debug(
            f"  AxisMouse: ({cfg.axis_x}, {cfg.axis_y})  "
            f"speed={cfg.speed}  deadzone={cfg.deadzone}  "
            f"accel={cfg.acceleration}  condición={cond_str}"
        )
    return result


# ══════════════════════════════════════════════════════════════════════
#  PERFIL POR DEFECTO (fallback si no se pasa --profile)
# ══════════════════════════════════════════════════════════════════════

DEFAULT_HOTKEYS: AbstractHotkeys = {
    ("hotkey", "start"):   KeyAction([ec.KEY_LEFTALT,  ec.KEY_F4]),
    ("hotkey", "select"):  KeyAction([ec.KEY_LEFTMETA]),
    ("hotkey", "a"):       KeyAction([ec.KEY_ESC]),
    ("hotkey", "b"):       KeyAction([ec.KEY_ENTER]),
    ("hotkey", "pageup"):  KeyAction([ec.KEY_LEFTCTRL, ec.KEY_LEFTALT, ec.KEY_T]),
    ("hotkey", "up"):      KeyAction([ec.KEY_VOLUMEUP]),
    ("hotkey", "down"):    KeyAction([ec.KEY_VOLUMEDOWN]),
    ("hotkey", "r3"):      ClickAction(ec.BTN_LEFT),
    ("hotkey", "l3"):      ClickAction(ec.BTN_RIGHT),
}

DEFAULT_AXIS_MOUSE: list[AxisMouseConfig] = [
    AxisMouseConfig(
        axis_x="joystick2left", axis_y="joystick2up",
        speed=800.0, deadzone=0.15, acceleration=1.5,
        condition=("hotkey",),
    ),
]

DEFAULT_COOLDOWN = 0.5


# ══════════════════════════════════════════════════════════════════════
#  GUID Y BÚSQUEDA DE MANDO
# ══════════════════════════════════════════════════════════════════════

def _sdl_guid_str(js: pygame.joystick.Joystick) -> str:
    return js.get_guid().lower().replace("-", "")

def find_joystick(guid: str, sdl_id: int) -> pygame.joystick.Joystick | None:
    matches = []

    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        js.init()
        js_guid = _sdl_guid_str(js)
        _logger.debug(f"  SDL joystick {i}: {js.get_name()}  GUID={js_guid}")

        if _guid_matches(js_guid, guid):
            matches.append((i, js))
        else:
            js.quit()

    if not matches:
        return None
    
    if len(matches) == 1:
        return matches[0][1]

    for device_i, js in matches:
        if device_i == sdl_id:
            return js

    return matches[0][1]

def list_gamepads():
    pygame.init()
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count == 0:
        _logger.error("No se encontraron gamepads.")
        _logger.error("Comprueba: sudo usermod -aG input $USER  (y vuelve a iniciar sesión)")
        return
    guid_counters: dict[str, int] = {}
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        js.init()
        guid = _sdl_guid_str(js)
        sdl_id = guid_counters.get(guid, 0)
        guid_counters[guid] = sdl_id + 1
        _logger.debug(f"  Nombre   : {js.get_name()}")
        _logger.debug(f"  GUID     : {guid}  ← usa este en --guid")
        _logger.debug(f"  sdl_id : {sdl_id}")
        _logger.debug(f"  Botones  : {js.get_numbuttons()}  Ejes: {js.get_numaxes()}  Hats: {js.get_numhats()}")
        _logger.debug("")
        js.quit()
    pygame.quit()


# ══════════════════════════════════════════════════════════════════════
#  BUCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

LOOP_HZ = 200
LOOP_DT = 1.0 / LOOP_HZ

# Rango de códigos BTN_* en el kernel (BTN_MISC=0x100 … BTN_TRIGGER_HAPPY39=0x2e7)
_BTN_MIN = 0x100
_BTN_MAX = 0x2e7

def _is_btn(code: int) -> bool:
    return _BTN_MIN <= code <= _BTN_MAX


@dataclass
class UInputPair:
    """
    Dos dispositivos UInput separados:
      kbd   → EV_KEY con KEY_* (teclado virtual)
      mouse → EV_KEY con BTN_* + EV_REL con REL_X/Y (ratón virtual)

    Separarlos es necesario porque el kernel/compositor clasifica el
    dispositivo al crearlo y un único UInput mezclado hace que los
    eventos BTN_LEFT sean ignorados como si fueran teclas de teclado.
    """
    kbd:   UInput | None
    mouse: UInput | None

    def write_key(self, code: int, value: int):
        """Envía EV_KEY al dispositivo correcto según el código."""
        if _is_btn(code):
            if self.mouse:
                self.mouse.write(ec.EV_KEY, code, value)
        else:
            if self.kbd:
                self.kbd.write(ec.EV_KEY, code, value)

    def write_rel(self, rel: int, value: int):
        if self.mouse:
            self.mouse.write(ec.EV_REL, rel, value)

    def syn(self, has_kbd: bool = False, has_mouse: bool = False):
        if has_kbd   and self.kbd:   self.kbd.syn()
        if has_mouse and self.mouse: self.mouse.syn()

    def close(self):
        if self.kbd:   self.kbd.close()
        if self.mouse: self.mouse.close()


def build_uinput(hotkeys: ResolvedHotkeys, axis_mouse: list[ResolvedAxisMouse], player) -> UInputPair:
    kbd_keys:   set[int] = set()
    mouse_btns: set[int] = set()
    has_rel = bool(axis_mouse)

    for action in hotkeys.values():
        for code in action.uinput_keys():
            if _is_btn(code):
                mouse_btns.add(code)
            else:
                kbd_keys.add(code)

    # Si hay movimiento de ratón también necesitamos BTN_LEFT declarado
    # para que el compositor reconozca el dispositivo como puntero.
    if has_rel:
        mouse_btns.add(ec.BTN_LEFT)

    kbd_uinput   = None
    mouse_uinput = None

    if kbd_keys:
        kbd_uinput = UInput(
            {ec.EV_KEY: list(kbd_keys)},
            name=f"gamepad-mapper-kbd-{player}",
        )
        _logger.debug(f"UInput teclado: {sorted(kbd_keys)}")

    if mouse_btns or has_rel:
        mouse_cap: dict[int, list[int]] = {}
        if mouse_btns: mouse_cap[ec.EV_KEY] = list(mouse_btns)
        mouse_cap[ec.EV_REL] = [ec.REL_X, ec.REL_Y]
        mouse_uinput = UInput(mouse_cap, name=f"gamepad-mapper-mouse-{player}")
        _logger.debug(f"UInput ratón: BTNs={sorted(mouse_btns)}")

    return UInputPair(kbd=kbd_uinput, mouse=mouse_uinput)


def mapper_loop(
    joystick:   pygame.joystick.Joystick,
    hotkeys:    ResolvedHotkeys,
    axis_mouse: list[ResolvedAxisMouse],
    cd_map:     CooldownMap,
    player
):
    ui = build_uinput(hotkeys, axis_mouse, player)

    pressed:      set[int]              = set()
    last_fired:   dict[frozenset, float] = {}
    fired_combos: set[frozenset]         = set()

    hat_active:  dict[tuple[int, int], int] = {}
    axis_active: dict[tuple[int, int], int] = {}
    axis_values: dict[int, float]           = {}

    mouse_accum_x = 0.0
    mouse_accum_y = 0.0

    last_tick = time.monotonic()

    _logger.info(f"Escuchando '{joystick.get_name()}'  GUID={_sdl_guid_str(joystick)}")
    _logger.info(f"{len(hotkeys)} hotkey(s)  {len(axis_mouse)} eje(s) de ratón")

    # combo → acción actualmente presionada (para enviar el release)
    active_holds: dict[frozenset[int], KeyAction | ClickAction | CallbackAction] = {}

    def check_and_press():
        """Al pulsar: busca el mejor combo y emite press_down."""
        now = time.monotonic()
        best = next(
            (combo for combo in sorted(hotkeys, key=len, reverse=True)
             if combo.issubset(pressed) and combo not in fired_combos),
            None
        )
        if best is None:
            return
        if now - last_fired.get(best, 0.0) < cd_map.get(best, 0.0):
            return
        last_fired[best] = now
        fired_combos.add(best)
        action = hotkeys[best]
        _logger.debug(f"▼ {' + '.join(hex(c) for c in sorted(best))}")
        action.press_down(ui)
        active_holds[best] = action

    def release(code: int):
        """Al soltar: libera el combo y emite press_up si estaba activo."""
        pressed.discard(code)
        nonlocal fired_combos
        # Liberar todos los combos que contengan este código
        to_release = {c for c in fired_combos if code in c}
        for combo in to_release:
            if combo in active_holds:
                _logger.debug(f"▲ {' + '.join(hex(c) for c in sorted(combo))}")
                active_holds.pop(combo).press_up(ui)
        fired_combos -= to_release

    def tick_mouse(dt: float):
        nonlocal mouse_accum_x, mouse_accum_y
        total_dx = 0.0
        total_dy = 0.0

        for cfg in axis_mouse:
            if cfg.condition is not None and not cfg.condition.issubset(pressed):
                continue

            # axis_sign es el "value" del es_input: -1 significa que el lado
            # "negativo" del eje físico corresponde a la dirección nombrada
            # (joystick2up → empujar arriba da valor SDL negativo → sign=-1).
            # Multiplicar por axis_sign normaliza el eje a convenio intuitivo:
            #   +1 = derecha / abajo,  -1 = izquierda / arriba.
            # REL_X/REL_Y de Linux usan el mismo convenio (+1 = derecha/abajo),
            # así que NO hay que invertir nada más.
            raw_x = axis_values.get(cfg.axis_id_x, 0.0) * cfg.axis_sign_x
            raw_y = axis_values.get(cfg.axis_id_y, 0.0) * cfg.axis_sign_y
            # Negar ambos ejes: tras la normalización anterior, empujar arriba
            # daba raw_y > 0, pero REL_Y > 0 mueve el ratón hacia abajo.
            raw_x = -raw_x
            raw_y = -raw_y

            def apply_curve(v: float) -> float:
                if abs(v) < cfg.deadzone:
                    return 0.0
                norm   = (abs(v) - cfg.deadzone) / (1.0 - cfg.deadzone)
                curved = math.copysign(norm ** cfg.acceleration, v)
                return curved

            total_dx += apply_curve(raw_x) * cfg.speed * dt
            total_dy += apply_curve(raw_y) * cfg.speed * dt

        mouse_accum_x += total_dx
        mouse_accum_y += total_dy

        ix = int(mouse_accum_x)
        iy = int(mouse_accum_y)
        if ix or iy:
            mouse_accum_x -= ix
            mouse_accum_y -= iy
            if ix: ui.write_rel(ec.REL_X, ix)
            if iy: ui.write_rel(ec.REL_Y, iy)
            ui.syn(has_mouse=True)

    try:
        while True:
            now = time.monotonic()
            dt  = now - last_tick
            last_tick = now

            for event in pygame.event.get():

                if event.type == pygame.JOYBUTTONDOWN:
                    pressed.add(_btn_code(event.button))
                    check_and_press()

                elif event.type == pygame.JOYBUTTONUP:
                    release(_btn_code(event.button))

                elif event.type == pygame.JOYHATMOTION:
                    key_hat = (event.joy, event.hat)
                    prev = hat_active.pop(key_hat, None)
                    if prev is not None:
                        release(prev)
                    hx, hy = event.value
                    if   hx ==  1: new = _hat_code(event.hat, 2)
                    elif hx == -1: new = _hat_code(event.hat, 8)
                    elif hy ==  1: new = _hat_code(event.hat, 1)
                    elif hy == -1: new = _hat_code(event.hat, 4)
                    else:          new = None
                    if new is not None:
                        hat_active[key_hat] = new
                        pressed.add(new)
                        check_and_press()

                elif event.type == pygame.JOYAXISMOTION:
                    axis_values[event.axis] = event.value

                    key_axis = (event.joy, event.axis)
                    prev = axis_active.pop(key_axis, None)
                    if prev is not None:
                        release(prev)
                    val = event.value
                    if   val >  AXIS_THRESHOLD: new = _axis_code(event.axis, positive=True)
                    elif val < -AXIS_THRESHOLD: new = _axis_code(event.axis, positive=False)
                    else:                       new = None
                    if new is not None:
                        axis_active[key_axis] = new
                        pressed.add(new)
                        check_and_press()

                elif event.type == pygame.JOYDEVICEREMOVED:
                    if event.instance_id == joystick.get_instance_id():
                        _logger.warning("JOYDEVICEREMOVED — mando activo desconectado, saliendo del loop.")
                        return
                    else:
                        _logger.debug(f"JOYDEVICEREMOVED — mando ajeno (instance_id={event.instance_id}), ignorado.")
            if axis_mouse:
                tick_mouse(dt)

            elapsed = time.monotonic() - now
            sleep   = LOOP_DT - elapsed
            if sleep > 0:
                time.sleep(sleep)

    except KeyboardInterrupt:
        pass
    finally:
        ui.close()


# ══════════════════════════════════════════════════════════════════════
#  ENTRADA
# ══════════════════════════════════════════════════════════════════════

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Gamepad hotkey mapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ejemplos:
  %(prog)s --list
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg --profile hotkeys.json
        """,
    )
    parser.add_argument("--list",     action="store_true")
    parser.add_argument("--guid",     metavar="GUID")
    parser.add_argument("--sdl_id", metavar="N", type=int, default=0,
                        help="Índice SDL cuando hay varios mandos con el mismo GUID (0-based).")
    parser.add_argument("--player",   metavar="N", type=int, default=1,
                        help="Número de jugador ES (1, 2, 3…): selecciona actions_playerN en el perfil.")
    parser.add_argument("--es-input", metavar="ARCHIVO")
    parser.add_argument("--profile",  metavar="ARCHIVO",
                        help="Perfil JSON de hotkeys (si se omite se usa el perfil por defecto).")
    parser.add_argument("--debug",    action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    pygame.init()
    pygame.joystick.init()

    if args.list:
        list_gamepads()
        pygame.quit()
        return

    if not args.guid:
        parser.error("Se requiere --guid")
    if not args.es_input:
        parser.error("Se requiere --es-input")

    # ── Cargar configuración ─────────────────────────────────────────
    if args.profile:
        try:
            hotkeys_abstract, axis_mouse_config, combo_cooldowns = load_profile(args.profile, args.player)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as ex:
            _logger.error(f"Error leyendo perfil: {ex}")
            pygame.quit()
            sys.exit(1)
    else:
        _logger.info("No se especificó --profile, usando perfil por defecto.")
        hotkeys_abstract  = DEFAULT_HOTKEYS
        axis_mouse_config = DEFAULT_AXIS_MOUSE
        # Perfil por defecto: botones únicos sin cooldown, combos con 0.5 s
        combo_cooldowns   = {
            names: (0.0 if len(names) == 1 else DEFAULT_COOLDOWN)
            for names in DEFAULT_HOTKEYS
        }

    # ── Parsear es_input.cfg ─────────────────────────────────────────
    try:
        es_map = parse_es_input(args.es_input, args.guid)
    except (FileNotFoundError, ET.ParseError, ValueError) as ex:
        _logger.error(f"Error leyendo es_input: {ex}")
        pygame.quit()
        sys.exit(1)

    _logger.debug("Resolución de hotkeys:")
    hotkeys, cd_map = resolve_hotkeys(hotkeys_abstract, es_map, combo_cooldowns)

    _logger.debug("Resolución de ejes de ratón:")
    axis_mouse = resolve_axis_mouse(axis_mouse_config, es_map)

    if not hotkeys and not axis_mouse:
        _logger.error("No se resolvió ninguna acción.")
        pygame.quit()
        sys.exit(1)

    # ── Bucle de reconexión ─────────────────────────────────────────
    # No termina si el mando se desconecta: espera y reanuda.
    # El proceso se mata externamente (SIGTERM) cuando ya no se necesite.
    RECONNECT_INTERVAL = 2.0
    first_attempt = True
    try:
        while True:
            joystick = find_joystick(args.guid, args.sdl_id)
            if joystick is None:
                if first_attempt:
                    _logger.warning(
                        f"Mando GUID={args.guid} no encontrado. "
                        f"Esperando conexión…"
                    )
                    first_attempt = False
                pygame.event.pump()
                time.sleep(RECONNECT_INTERVAL)
                continue

            first_attempt = True
            _logger.info(
                f"Mando conectado: '{joystick.get_name()}'  "
                f"(player={args.player}, sdl_id={args.sdl_id})"
            )
            try:
                mapper_loop(joystick, hotkeys, axis_mouse, cd_map, args.player)
            except Exception as exc:
                _logger.error(f"Error inesperado: {exc}", exc_info=True)
            finally:
                try:
                    joystick.quit()
                except Exception:
                    pass
            _logger.warning("Mando desconectado, esperando reconexión…")
            pygame.event.pump()
            time.sleep(RECONNECT_INTERVAL)

    except KeyboardInterrupt:
        _logger.info("Detenido por el usuario.")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
