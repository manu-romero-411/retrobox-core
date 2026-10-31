"""Which ``rendering-defaults.yml`` a game uses, from its shader set.

The shader sets live in ``<shaders dir>/configs/<set>/rendering-defaults.yml``
(downloaded from retrobox-shaders). EmulationStation's SHADER SET option has
three kinds of values:

* a set name: that set;
* ``none``: ``configs/rendering-defaults.yml`` itself, which sets no shader
  (only things such as the Game Boy colorization);
* AUTO (the option unset, empty or ``auto``): the set named by the ``auto``
  key of ``configs/rendering-defaults.yml`` (``retro`` in retrobox-shaders),
  or that file itself if it names none.

A set that isn't installed falls back to ``configs/rendering-defaults.yml``,
with a warning, so the game still starts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

import yaml

_logger = logging.getLogger(__name__)

NONE: Final = "none"
_AUTO_VALUES: Final = frozenset({"", "auto"})
_AUTO_KEY: Final = "auto"
_FILE: Final = "rendering-defaults.yml"


def _auto_set(base: Path) -> str:
    """The set the base file names for AUTO (empty if none)."""
    try:
        data = yaml.safe_load(base.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return ""
    value = data.get(_AUTO_KEY) if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else ""


def rendering_defaults(shaders_dir: Path, shader_set: object) -> Path:
    """The rendering-defaults.yml for ``shader_set``.

    Args:
        shaders_dir: The shaders directory (its ``configs`` holds the sets).
        shader_set: The ``shaderset`` option of the game, as configured (any
            non-string, e.g. a missing value, counts as AUTO).

    Returns:
        The file to load (it may not exist if no shaders are installed: the
        caller then gets no rendering defaults, as before).
    """
    configs = shaders_dir / "configs"
    base = configs / _FILE
    name = shader_set.strip() if isinstance(shader_set, str) else ""
    if name in _AUTO_VALUES:
        name = _auto_set(base)
        if not name:
            return base
        _logger.debug("shader set AUTO is %s", name)
    if name == NONE:
        return base

    chosen = configs / name / _FILE
    if not chosen.is_file():
        _logger.warning("shader set %s is not installed (%s); using no shader set", name, chosen)
        return base
    return chosen
