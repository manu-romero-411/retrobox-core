"""
GamepadManager — context manager que lanza/mata instancias de mapper.py
por cada controller activo, usando el mismo sistema de búsqueda de perfiles
que evmapy de batocera.

Jerarquía de búsqueda de perfiles (primer match gana):
    {rom}.keys                              ← override por juego
    profiles/{system}.{emulator}.{core}.keys
    profiles/{system}.{emulator}.keys
    profiles/{system}.keys
    profiles/{emulator}.keys
    profiles/any.keys                       ← fallback global
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from runtime.retrobox_paths import (
    _MAPPER_SCRIPT,
    _PROFILES_DIR,
    _PROFILES_USER_DIR,
    ES_INPUT
)

if TYPE_CHECKING:
    from types import TracebackType
    from runtime.launcher.configgen.controller import Controller, Controllers

_logger = logging.getLogger(__name__)

def _find_profile(rom: Path, system: str, emulator: str, core: str) -> Path | None:
    candidates = [
        (rom.parent / f"{rom.name}.keys") if not rom.is_dir() else (rom / "pad2.keys"),
        _PROFILES_USER_DIR / f"{system}.{emulator}.{core}.keys",
        _PROFILES_USER_DIR / f"{system}.{emulator}.keys",
        _PROFILES_USER_DIR / f"{system}.keys",
        _PROFILES_USER_DIR / f"{emulator}.keys",
        _PROFILES_USER_DIR / "any.keys",
        _PROFILES_DIR / f"{system}.{emulator}.{core}.keys",
        _PROFILES_DIR / f"{system}.{emulator}.keys",
        _PROFILES_DIR / f"{system}.keys",
        _PROFILES_DIR / f"{emulator}.keys",
        _PROFILES_DIR / "any.keys",

    ]
    for path in candidates:
        _logger.debug("gamepadly: comprobando perfil de mando en %s", path)
        if path.exists():
            _logger.debug("gamepadly: perfil → %s", path)
            return path
    _logger.debug(
        "gamepadly: sin perfil para system=%s emulator=%s core=%s",
        system, emulator, core)
    return None


@dataclass
class GamepadManager(AbstractContextManager):
    """
    Lanza una instancia de mapper.py por cada controller en `controllers`
    y las termina al salir del contexto.

    Si no se encuentra ningún perfil .keys no lanza nada (no-op silencioso).
    """

    system:      str
    emulator:    str
    core:        str
    rom:         Path
    controllers: "Controllers"
    es_input:    Path | None = None

    _processes: list[subprocess.Popen] = field(default_factory=list, init=False, repr=False)

    def __enter__(self) -> "GamepadManager":
        self._stop_all()

        profile = _find_profile(self.rom, self.system, self.emulator, self.core)
        if profile is None:
            return self

        es_input = self.es_input or ES_INPUT
        if not es_input.exists():
            _logger.warning("gamepadly: es_input no encontrado en %s", es_input)
            return self

        for controller in self.controllers:
            # Solo joysticks, no teclados
            if getattr(controller, "type", "joystick") == "keyboard":
                continue
            self._launch(controller, profile, es_input)

        return self

    def __exit__(
        self,
        exc_type: "type[BaseException] | None",
        exc_value: "BaseException | None",
        traceback: "TracebackType | None",
    ) -> None:
        self._stop_all()

    def _launch(self, controller: "Controller", profile: Path, es_input: Path) -> None:
        guid  = controller.guid
        index = controller.index          # índice SDL (0-based), mismo que pasó ES
        player = controller.player_number  # 1-based, selecciona actions_player{N} en el perfil

        if not guid:
            _logger.warning("gamepadly: controller sin GUID (player=%d), saltando", player)
            return

        cmd = [
            sys.executable,
            str(_MAPPER_SCRIPT),
            "--guid",     guid,
            "--sdl_id",   str(index),
            "--player",   str(player),
            "--es-input", str(es_input),
            "--profile",  str(profile),
        ]

        _logger.info(
            "gamepadly: player=%d guid=%s sdl_id=%d perfil=%s",
            player, guid, index, profile.name,
        )
        _logger.debug("gamepadly: cmd=%s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # desacoplar del proceso padre
            )
            self._processes.append(proc)
            _logger.debug("gamepadly: PID %d lanzado", proc.pid)
        except OSError as ex:
            _logger.error("gamepadly: error lanzando mapper: %s", ex)

    def _stop_all(self) -> None:
        for proc in self._processes:
            if proc.poll() is None:
                _logger.debug("gamepadly: terminando PID %d", proc.pid)
                try:
                    proc.send_signal(signal.SIGTERM)
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    _logger.warning("gamepadly: PID %d no terminó, matando", proc.pid)
                    proc.kill()
                except OSError:
                    pass
        self._processes.clear()
