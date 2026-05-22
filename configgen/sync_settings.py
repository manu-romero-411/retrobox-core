#!/usr/bin/env python3
"""Sincroniza es_settings.cfg → batocera.conf antes de lanzar un emulador."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from .batoceraPaths import BATOCERA_CONF, ES_SETTINGS

_logger = logging.getLogger(__name__)

# Keys de ES que no son configuración de emuladores
_SKIP_PREFIXES = (
    'INPUT ', 'Last', 'Show', 'Theme', 'Audio', 'Brightness',
    'Clock', 'Power', 'Scraper', 'UI', 'Video', 'Window',
)

def sync() -> None:
    if not ES_SETTINGS.exists():
        _logger.warning("es_settings.cfg no encontrado en %s", ES_SETTINGS)
        return

    try:
        tree = ET.parse(ES_SETTINGS)
        # Mapeo de keys de ES → keys de batocera.conf
        KEY_MAP = {
            'Language': 'system.language',
        }

        lines = []
        for el in tree.getroot():
            name  = el.get('name', '')
            value = el.get('value', '')
            if any(name.startswith(p) for p in _SKIP_PREFIXES):
                continue
            name = KEY_MAP.get(name, name)  # traducir si hay mapeo
            lines.append(f'{name}={value}')

        #BATOCERA_CONF.parent.mkdir(parents=True, exist_ok=True)
        with open(BATOCERA_CONF, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        _logger.debug("batocera.conf sincronizado (%d entradas)", len(lines))
    except Exception:
        _logger.exception("Error sincronizando es_settings → batocera.conf")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    sync()