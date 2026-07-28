"""
This submodule regenerates es_systems.cfg based on actual system directories situation
"""
import logging
import os
from pathlib import Path
import sys
from typing import Final
import xml.etree.ElementTree as ET
from xml.dom import minidom
import yaml
from yaml.scanner import ScannerError
from yaml.parser import ParserError

ROOTDIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOTDIR))

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
_logger = logging.getLogger(__name__)

from runtime.retrobox_paths import (
    _ES_SYSTEMS_DIR,
    ES_SYSTEMS_CFG,
    ROMS,
    USERDATA
)

PYTHON_COMMAND: Final = Path("/usr/bin/python3")
EMULAUNCHER_COMMAND: Final = USERDATA / "runtime" / "launcher" / "emulatorlauncher.py"
DEFAULT_COMMAND = [
    str(PYTHON_COMMAND),
    str(EMULAUNCHER_COMMAND),
    "%CONTROLLERSCONFIG%",
    "-system", "%SYSTEM%",
    "-rom", "%ROM%",
    "-gameinfoxml", "%GAMEINFOXML%",
    "-systemname", "%SYSTEMNAME%"
]

def _build_core_attributes(core_props):
    """Extrae y formatea los atributos de un core (default, incompatible_extensions)."""
    core_attrs = {}
    if not isinstance(core_props, dict):
        return core_attrs

    if core_props.get("default") is True:
        core_attrs["default"] = "true"

    incompatibles = core_props.get("incompatible_extensions")
    if incompatibles:
        if isinstance(incompatibles, list):
            core_attrs["incompatible_extensions"] = " ".join(incompatibles)
        else:
            core_attrs["incompatible_extensions"] = str(incompatibles)

    return core_attrs

def _append_emulator_nodes(parent_elem, emulators_data):
    """Procesa y añade los nodos de emuladores y sus respectivos cores."""
    if not isinstance(emulators_data, dict):
        return

    for emu_name, emu_data in emulators_data.items():
        emulator_elem = ET.SubElement(parent_elem, "emulator", name=emu_name)

        if not isinstance(emu_data, dict):
            continue

        for core_name, core_props in emu_data.items():
            core_attrs = _build_core_attributes(core_props)
            core_elem = ET.SubElement(emulator_elem, "core", **core_attrs)
            core_elem.text = core_name

def generate_es_systems(base_path: Path = _ES_SYSTEMS_DIR, output_path: Path = ES_SYSTEMS_CFG):
    """
    Recorre la estructura de directorios YAML generada y reconstruye 
    el archivo es_systems.cfg original.
    """
    _logger.info("Start generating %s", output_path)
    base_dir: str = str(base_path)
    output_cfg_file: str = str(output_path)

    root = ET.Element("systemList")

    # Forzar la ruta a string para evitar falsos positivos de iteración en linters
    safe_base_dir = os.fspath(base_dir)

    for root_dir, _, files in os.walk(safe_base_dir):
        for file in files:
            if not file.endswith(".yaml"):
                continue

            yaml_path = os.path.join(root_dir, file)
            try:
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            except (ScannerError, ParserError) as e:
                _logger.error("Error de sintaxis en YAML al leer %s: %s", yaml_path, e)
                continue

            if not isinstance(data, dict) or not data:
                continue

            sys_name, sys_content = next(iter(data.items()))

            system_elem = ET.SubElement(root, "system")
            name_elem = ET.SubElement(system_elem, "name")
            name_elem.text = sys_name

            if "path" not in sys_content:
                sys_content["path"] = str(Path(f"{ROMS}/{sys_name}"))

            # Asegurar que el campo 'command' esté presente si no viene en el YAML
            if "command" not in sys_content:
                sys_content["command"] = " ".join(DEFAULT_COMMAND)

            for key, value in sys_content.items():
                if key == "name":
                    continue

                child_elem = ET.SubElement(system_elem, key)

                if key in ["platform", "extension"]:
                    child_elem.text = " ".join(value) if isinstance(value, list) else str(value)
                elif key == "emulators":
                    _append_emulator_nodes(child_elem, value)
                else:
                    child_elem.text = str(value) if value is not None else ""

    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="\t", encoding="utf-8")

    decoded_xml = pretty_xml.decode('utf-8')
    clean_lines = []

    for line in decoded_xml.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("<?xml"):
            clean_lines.append(line)

    final_lines = ['<?xml version="1.0" encoding="UTF-8"?>'] + clean_lines
    final_xml = "\n".join(final_lines)

    with open(output_cfg_file, 'w', encoding='utf-8') as f:
        f.write(final_xml)

    _logger.info("Successfully regenerated: %s", output_cfg_file)
