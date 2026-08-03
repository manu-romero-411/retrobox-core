from __future__ import annotations

# (label en el bml, name interno, target_dir opcional)
_GAMEPAD_MAPPING: list[tuple[str, str, str | None]] = [
    ("Pad.Up", "up", None),
    ("Pad.Down", "down", None),
    ("Pad.Left", "left", None),
    ("Pad.Right", "right", None),
    ("Select", "select", None),
    ("Start", "start", None),
    ("A..South", "b", None),
    ("B..East", "a", None),
    ("X..West", "y", None),
    ("Y..North", "x", None),
    ("L-Bumper", "pageup", None),
    ("R-Bumper", "pagedown", None),
    ("L-Trigger", "l2", "/Hi"),
    ("R-Trigger", "r2", "/Hi"),
    ("L-Stick..Click", "l3", None),
    ("R-Stick..Click", "r3", None),
    ("L-Up", "joystick1up", "/Lo"),
    ("L-Down", "joystick1up", "/Hi"),
    ("L-Left", "joystick1left", "/Lo"),
    ("L-Right", "joystick1left", "/Hi"),
    ("R-Up", "joystick2up", "/Lo"),
    ("R-Down", "joystick2up", "/Hi"),
    ("R-Left", "joystick2left", "/Lo"),
    ("R-Right", "joystick2left", "/Hi"),
]


def _ares_get_ctrler_entry(name, guid, inputs, target_dir=None) -> str:
    """
    Traduce un input lógico (ej. 'up', 'l2') al formato de entrada de
    ares para VirtualPad (guid/puerto/tipo/id[+dirección]).
    Devuelve "" si el control no está mapeado en este pad.
    """
    if name not in inputs:
        return ""

    i = inputs[name]
    itype = getattr(i, 'type', None)
    iid = getattr(i, 'id', '0')
    ival = str(getattr(i, 'value', '1'))

    if itype == 'button':
        return f"{guid}/0/3/{iid}"
    if itype == 'hat':
        hat_id = '1' if name in ('up', 'down') else '0'
        direction = "/Lo" if name in ('up', 'left') else "/Hi"
        return f"{guid}/0/1/{hat_id}{direction}"
    if itype == 'axis':
        direction = target_dir or ("/Hi" if ival.startswith('-') or int(float(ival)) > 0 else "/Lo")
        return f"{guid}/0/0/{iid}{direction}"
    return ""


def _ares_gen_gamepad_conf(pad_num: int, guid: str, inputs) -> str:
    """Genera el bloque VirtualPadN completo para un controller."""
    lines = [f"VirtualPad{pad_num}"]
    for label, name, target_dir in _GAMEPAD_MAPPING:
        entry = _ares_get_ctrler_entry(name, guid, inputs, target_dir)
        lines.append(f"  {label}: {entry};;")
    lines.append("  Rumble: ;;")
    return "\n".join(lines) + "\n"


def _ares_create_pads_config(playersControllers) -> str:
    """Genera el mapeo de hasta 5 controles para el settings.bml de ares."""
    pads_config = ""
    for index, controller in enumerate(playersControllers):
        if index >= 5:
            break
        pad_num = index + 1
        pads_config += _ares_gen_gamepad_conf(pad_num, controller.guid, controller.inputs)
    return pads_config