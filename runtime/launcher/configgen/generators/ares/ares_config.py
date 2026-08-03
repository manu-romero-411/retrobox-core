from __future__ import annotations

import logging
from pathlib import Path

from .ares_controllers import _ares_create_pads_config
from .ares_paths import _ARES_CFG, _ARES_CFGDIR, _ARES_EMUDIR, _ARES_SAVES, _ARES_SCREENSHOTS, _ARES_SHADERS_DIR

_logger = logging.getLogger(__name__)


def _ares_resolve_shader(shader_id, shaders_dir: Path) -> str:
    """
    Resuelve el shader a usar a partir del render_config compartido con
    RetroArch (system.renderconfig), para que la elección de shader sea
    la misma sin importar el emulador usado.

    render_config trae algo como {'shader': 'crt/crt-hyllian-ntsc-2', ...},
    sin extensión. Acá la completamos con .slangp y validamos que el
    archivo exista de verdad en share/ares/Shaders antes de escribirlo,
    para no romper el arranque de ares si el shader no está deployado.
    """
    if not shader_id:
        return "None"

    rel_path = f"{shader_id}.slangp"
    if not (shaders_dir / rel_path).is_file():
        _logger.warning(
            "Ares shader '%s' not found at %s, falling back to None",
            rel_path, shaders_dir,
        )
        return "None"

    return shader_id


def _saves_path_for(system) -> str:
    """
    OJO: la barra final es obligatoria. Sin ella, ares concatena el
    nombre "bonito" del sistema al último componente de la ruta
    (ej: ".../saves/n64" + "Nintendo 64" -> ".../saves/n64Nintendo 64")
    en vez de crearlo como subcarpeta real.
    """
    return f"{_ARES_SAVES / system.name}/"


def _build_bml_content(system, saves_path: str) -> str:
    video_driver = system.config.get("ares_video_driver", "OpenGL 3.2")
    audio_driver = system.config.get("ares_audio_driver", "SDL")

    return f"""Video
  Driver: {video_driver}
  Monitor: Primary
  Format: ARGB24
  Exclusive: false
  Blocking: false
  Flush: false
  Multiplier: 2
  Output: Scale
  AspectCorrection: true
  AdaptiveSizing: true
  AutoCentering: false
  Luminance: 1.0
  Saturation: 1.0
  Gamma: 1.0
  ColorBleed: false
  ColorEmulation: true
  InterframeBlending: true
  Overscan: false
  PixelAccuracy: false
  Quality: SD
  Supersampling: false
  DisableVideoInterfaceProcessing: false
  WeaveDeinterlacing: true
  PresentSRGB: false
  ThreadedRenderer: true
  NativeFullScreen: true
  WindowWidth: 800
  WindowHeight: 576
  FixedScale: 2
  AspectCorrectionMode: Standard
Audio
  Driver: {audio_driver}
  Device: Default
  Frequency: 48000
  Latency: 40
  Exclusive: false
  Blocking: true
  Dynamic: false
  Mute: false
  Volume: 1.0
  Balance: 0.0
Input
  Driver: SDL
  Defocus: Pause
Boot
  Fast: false
  Debugger: false
  Prefer: NTSC-U
  AwaitGDBClient: false
General
  ShowStatusBar: true
  Rewind: false
  RunAhead: false
  AutoSaveMemory: true
  HomebrewMode: false
  NoFilePrompt: true
Paths
  Home: {_ARES_CFGDIR}/
  Saves: {saves_path}
  Screenshots: {_ARES_SCREENSHOTS}
"""


def write_ares_config(system, playersControllers) -> None:
    """
    Punto de entrada único: arma el settings.bml completo (video/audio/
    input/paths + mapeo de controles) y lo escribe a disco.
    """
    saves_path = _saves_path_for(system)

    bml_content = _build_bml_content(system, saves_path)
    bml_content += _ares_create_pads_config(playersControllers)

    _ARES_CFG.write_text(bml_content, encoding="utf-8")