"""Data shared by every step of one game launch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    from configgen.batoceraTypes import Resolution
    from configgen.controller import Controller
    from configgen.Emulator import Emulator
    from configgen.generators.Generator import Generator
    from configgen.gun import Guns

    from .controller_monitor import ControllerMonitor


@dataclass
class GameInputs:
    """The input devices of a game, and the watcher that follows them."""

    controllers: list[Controller]
    guns: Guns
    wheels: Any
    monitor: ControllerMonitor


@dataclass
class GameSession:
    """Everything needed to run one game, shared by the launch helpers."""

    args: argparse.Namespace
    system: Emulator
    generator: Generator
    rom: Path
    resolution: Resolution
    metadata: dict[str, str]
    inputs: GameInputs


def effective_core(system: Emulator) -> str:
    """Return the configured core, or an empty string if there is none."""
    if "core" in system.config and system.config.core is not None:
        return system.config.core
    return ""
