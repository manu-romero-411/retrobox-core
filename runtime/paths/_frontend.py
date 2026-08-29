"""
Constantes de runtime.paths para el frontend (EmulationStation):
ubicación del binario, archivos de configuración generados y metadata de
recursos (guns/wheels/gamesdb).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from ._base import DEFAULTS_DIR, RETROBOX_ROOTDIR

FRONTEND_DIR: Final = RETROBOX_ROOTDIR / "frontend"

_USER_ES_DIR: Final = FRONTEND_DIR / ".emulationstation"
ES_SETTINGS_CFG: Final = _USER_ES_DIR / "es_settings.cfg"
ES_FEATURES_CFG: Final = _USER_ES_DIR / "es_features.cfg"
ES_SYSTEMS_CFG: Final = _USER_ES_DIR / "es_systems.cfg"
ES_FEATURES_TMP: Final = Path("/tmp/retrobox_es_features.cfg")
ES_SYSTEMS_TMP: Final = Path("/tmp/retrobox_es_systems.cfg")
ES_INPUT_CFG: Final = _USER_ES_DIR / "es_input.cfg"
ES_INI_TMP: Final = Path("/tmp/retrobox-emulationstation.ini")
ES_INI_CFG: Final = _USER_ES_DIR / "emulationstation.ini"
ES_EXECUTABLE: Final = FRONTEND_DIR / "emulationstation"

# Recursos de ES y configgen (sistema)
_ES_RESOURCES_DIR: Final = FRONTEND_DIR / "resources"
ES_GUNS_METADATA: Final = _ES_RESOURCES_DIR / "gungames.xml"
ES_WHEELS_METADATA: Final = _ES_RESOURCES_DIR / "wheelgames.xml"
ES_GAMES_METADATA: Final = _ES_RESOURCES_DIR / "gamesdb.xml"
ES_GUNS_ART_METADATA: Final = DEFAULTS_DIR / "data" / "gamesbuttonsdb.xml"