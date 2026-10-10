"""Ares configuration: settings.bml.

Ares reads one settings file (BML, nested by name) that this module writes in
full on every launch. The options of the menu fill the settings that exist in
Ares, and each one has the default the file used before the menu was wired, so
a game that sets nothing runs as it always did.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...utils.audio_gain import gain_to_percent
from .ares_controllers import _ares_create_pads_config
from .ares_paths import _ARES_CFG, _ARES_CFGDIR, _ARES_SAVES, _ARES_SCREENSHOTS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from ...config import SystemConfig
    from ...Emulator import Emulator

_logger = logging.getLogger(__name__)

DEFAULT_VIDEO_DRIVER = "OpenGL 3.2"
OUTPUT_STRETCH = "Stretch"
ASPECT_ANAMORPHIC = "Anamorphic"

_MAX_VOLUME = 200  # Ares can amplify up to twice the volume (+6 dB)
_AUTO_VALUES = ("", "auto")
_DEFAULT_PAK_SIZE = "32KiB (Default)"
_DEFAULT_QUALITY = "SD"  # 1x native; HD is 2x and UHD is 4x

# the controllers of the SNES ports Ares can remember: menu option -> Ares setting
_SNES_PORTS = {"ares_snes_port1": "ControllerPort1", "ares_snes_port2": "ControllerPort2"}

Section = dict[str, object]


def resolve_shader(shader_id: str | None, shaders_dir: Path) -> str:
    """Return the shader to use, or "None" if it is not set or not installed.

    The shader choice is shared with RetroArch (``system.renderconfig``), so it
    is the same whatever emulator runs. The id comes without extension, and the
    ``.slangp`` file must exist in share/ares/Shaders: a missing one must not
    break the start of Ares.
    """
    if not shader_id:
        return "None"

    rel_path = f"{shader_id}.slangp"
    if not (shaders_dir / rel_path).is_file():
        _logger.warning(
            "Ares shader '%s' not found at %s, falling back to None", rel_path, shaders_dir
        )
        return "None"
    return shader_id


def _saves_path_for(system: Emulator) -> str:
    """Return the saves folder of the system.

    The trailing slash is required: without it Ares appends the pretty name of
    the system to the last folder (".../saves/n64" + "Nintendo 64" becomes
    ".../saves/n64Nintendo 64") instead of creating a real subfolder.
    """
    return f"{_ARES_SAVES / system.name}/"


def _value(config: SystemConfig, key: str, default: str) -> str:
    """Return an option as text, with the default when it is unset or on "auto"."""
    value = str(config.get(key, default))
    return default if value in _AUTO_VALUES else value


def video_driver(config: SystemConfig) -> str:
    """Return the video driver of Ares ("OpenGL 3.2" is the only one on Linux)."""
    return _value(config, "ares_video_driver", DEFAULT_VIDEO_DRIVER)


def output_mode(config: SystemConfig) -> str:
    """Return how the picture fills the window: Scale, Integer or Stretch."""
    return _value(config, "ares_output", "Scale")


def aspect_correction(config: SystemConfig) -> str:
    """Return the aspect correction: None, Standard or Anamorphic."""
    return _value(config, "ares_aspect_correction", "Standard")


def _video_section(config: SystemConfig) -> Section:
    """Build the [Video] section."""
    return {
        "Driver": video_driver(config),
        "Monitor": "Primary",
        "Format": "ARGB24",
        "Exclusive": False,
        "Blocking": config.get_bool("use_vsync"),
        "Flush": False,
        "Multiplier": 2,
        "Output": output_mode(config),
        "AspectCorrection": True,
        "AdaptiveSizing": True,
        "AutoCentering": False,
        "Luminance": "1.0",
        "Saturation": "1.0",
        "Gamma": "1.0",
        "ColorBleed": False,
        "ColorEmulation": config.get_bool("ares_color_emulation", True),
        "InterframeBlending": config.get_bool("ares_interframe_blending", True),
        "Overscan": False,
        "PixelAccuracy": False,
        "PresentSRGB": False,
        "ThreadedRenderer": config.get_bool("ares_threaded_renderer", True),
        "NativeFullScreen": True,
        "WindowWidth": 800,
        "WindowHeight": 576,
        "FixedScale": 2,
        "AspectCorrectionMode": aspect_correction(config),
    }


def _volume(config: SystemConfig) -> str:
    """Return the Ares volume (1.0 is the normal one) for the audio gain of the game."""
    percent = gain_to_percent(config.get("ares_audio_gain", "0"), _MAX_VOLUME)
    return str(round(percent / 100, 3))


def _audio_section(config: SystemConfig) -> Section:
    """Build the [Audio] section."""
    return {
        "Driver": _value(config, "ares_audio_driver", "SDL"),
        "Device": "Default",
        "Frequency": 48000,
        "Latency": _value(config, "ares_audio_latency", "40"),
        "Exclusive": False,
        "Blocking": True,
        "Dynamic": False,
        "Mute": False,
        "Volume": _volume(config),
        "Balance": "0.0",
    }


def _nintendo64_section(config: SystemConfig) -> Section:
    """Build the [Nintendo64] section: memory, Controller Pak size and render quality."""
    quality = _value(config, "ares_n64_quality", _DEFAULT_QUALITY)
    # supersampling scales 2x and 4x back to native, and does not work with weave deinterlacing
    supersampling = config.get_bool("ares_n64_supersampling") and quality != _DEFAULT_QUALITY
    return {
        "ExpansionPak": config.get_bool("ares_n64_expansion_pak", True),
        "ControllerPakBankString": _value(config, "ares_n64_cpak_size", _DEFAULT_PAK_SIZE),
        "Quality": quality,
        "Supersampling": supersampling,
        "DisableVideoInterfaceProcessing": False,
        "WeaveDeinterlacing": not supersampling,
    }


def _peripherals(config: SystemConfig, ports: Mapping[str, str]) -> Section:
    """Return the controllers the game picked for the ports; the others keep Ares' choice."""
    return {
        setting: str(config.get(key))
        for key, setting in ports.items()
        if str(config.get(key, "")) not in _AUTO_VALUES
    }


def _super_famicom_section(config: SystemConfig) -> Section:
    """Build the [SuperFamicom] section: deep black boost and the controllers."""
    return {
        "DeepBlackBoost": config.get_bool("ares_sfc_deep_black_boost"),
        **_peripherals(config, _SNES_PORTS),
    }


def build_settings(config: SystemConfig, saves_path: str) -> dict[str, Section]:
    """Build every section of settings.bml for a game."""
    return {
        "Video": _video_section(config),
        "Audio": _audio_section(config),
        "Input": {"Driver": "SDL", "Defocus": "Pause"},
        "Boot": {
            "Fast": config.get_bool("ares_fast_boot"),
            "Debugger": False,
            "Prefer": "NTSC-U",
            "AwaitGDBClient": False,
        },
        "General": {
            "ShowStatusBar": True,
            "Rewind": config.get_bool("ares_rewind"),
            "RunAhead": config.get_bool("ares_run_ahead"),
            "AutoSaveMemory": True,
            "HomebrewMode": False,
            "NoFilePrompt": True,
        },
        "Nintendo64": _nintendo64_section(config),
        "SuperFamicom": _super_famicom_section(config),
        "MegaDrive": {"TMSS": config.get_bool("ares_md_tmss")},
        "Paths": {
            "Home": f"{_ARES_CFGDIR}/",
            "Saves": saves_path,
            "Screenshots": _ARES_SCREENSHOTS,
        },
    }


def render_bml(sections: Mapping[str, Section]) -> str:
    """Write the sections as BML text."""
    lines: list[str] = []
    for name, options in sections.items():
        lines.append(name)
        for key, value in options.items():
            text = str(value).lower() if isinstance(value, bool) else str(value)
            lines.append(f"  {key}: {text}")
    return "\n".join(lines) + "\n"


def write_ares_config(system: Emulator, players_controllers) -> None:
    """Write settings.bml: the settings of the game followed by the controller mapping."""
    sections = build_settings(system.config, _saves_path_for(system))
    content = render_bml(sections) + _ares_create_pads_config(players_controllers)
    _ARES_CFG.write_text(content, encoding="utf-8")
