"""The rendering defaults (shader, scanline, colorization...) of a game.

They come from ``rendering-defaults.yml`` files in ``<shaders dir>/configs``
(downloaded from retrobox-shaders), each one with a ``default`` section and
optional per-system sections:

* ``configs/rendering-defaults.yml``, the base: what applies whatever the
  shader set, such as the Game Boy colorization. It sets no shader.
* ``configs/<set>/rendering-defaults.yml``: a shader set (shaders, scanlines).

The base is always loaded and the chosen set, if any, is layered on top of it,
so the fields the set doesn't define (e.g. ``colorization``) are kept. A
system's own section beats any ``default`` section, whichever file it comes
from: ``default`` of the base < ``default`` of the set < the system in the base
< the system in the set. Each file may have a ``rendering-defaults-arch.yml``
next to it, layered right after it.

EmulationStation's SHADER SET option picks the set:

* a set name: that set;
* ``none``: no set, just the base;
* AUTO (the option unset, empty or ``auto``): the set named by the ``auto``
  key of the base (``retro`` in retrobox-shaders), or no set if it names none.

A set that isn't installed is skipped with a warning, so the game still starts.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import yaml

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = logging.getLogger(__name__)

NONE: Final = "none"
_AUTO_VALUES: Final = frozenset({"", "auto"})
_AUTO_KEY: Final = "auto"
_FILE: Final = "rendering-defaults.yml"
_ARCH_FILE: Final = "rendering-defaults-arch.yml"


def _read(path: Path) -> dict[str, Any]:
    """A YAML mapping, empty if the file is missing or not a mapping."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        if path.exists():
            _logger.warning("Cannot read %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _merge(destination: dict[str, Any], source: Mapping[str, Any]) -> None:
    """Recursive dict update: nested mappings are merged, not replaced."""
    for key, value in source.items():
        if isinstance(destination.get(key), dict) and isinstance(value, Mapping):
            _merge(destination[key], value)
        else:
            destination[key] = value


def rendering_files(shaders_dir: Path, shader_set: object) -> list[Path]:
    """The rendering-defaults.yml files of ``shader_set``, lowest priority first.

    Args:
        shaders_dir: The shaders directory (its ``configs`` holds the files).
        shader_set: The ``shaderset`` option of the game, as configured (any
            non-string, e.g. a missing value, counts as AUTO).

    Returns:
        The base file, then the set's one if a set applies. They may not
        exist (no shaders installed): they just add nothing then.
    """
    configs = shaders_dir / "configs"
    base = configs / _FILE
    name = shader_set.strip() if isinstance(shader_set, str) else ""
    if name in _AUTO_VALUES:
        auto = _read(base).get(_AUTO_KEY)
        name = auto.strip() if isinstance(auto, str) else ""
        _logger.debug("shader set AUTO is %s", name or NONE)
    if not name or name == NONE:
        return [base]

    chosen = configs / name / _FILE
    if not chosen.is_file():
        _logger.warning("shader set %s is not installed (%s); using no shader set", name, chosen)
        return [base]
    return [base, chosen]


def load_rendering_defaults(system: str, files: Sequence[Path]) -> dict[str, Any]:
    """Merge the ``default`` and ``system`` sections of ``files`` (see the
    module docstring for the order)."""
    layers = [_read(path.with_name(name)) for path in files for name in (_FILE, _ARCH_FILE)]
    config: dict[str, Any] = {}
    for section in ("default", system):
        for layer in layers:
            values = layer.get(section)
            if isinstance(values, Mapping):
                _merge(config, values)
    return config


def rendering_defaults(shaders_dir: Path, system: str, shader_set: object) -> dict[str, Any]:
    """The rendering defaults of ``system`` with ``shader_set`` (see above)."""
    return load_rendering_defaults(system, rendering_files(shaders_dir, shader_set))
