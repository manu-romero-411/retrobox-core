"""
This submodule regenerates es_systems.cfg based on actual system directories situation
"""
import logging
import os
from pathlib import Path
from typing import Final
import xml.etree.ElementTree as ET
from xml.dom import minidom
import yaml
from yaml.scanner import ScannerError
from yaml.parser import ParserError

# logging.basicConfig(
#     level=logging.INFO,
#     format="[%(levelname)s] %(message)s"
# )
_logger = logging.getLogger(__name__)

from runtime.retrobox_paths import (
    _SYSTEMS_CONF_DIR,
    ES_SYSTEMS_CFG,
    ES_SYSTEMS_TMP,
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
    """Procesa y añade los nodos de emuladores y sus 
    respectivos cores ignorando las opciones internas."""
    if not isinstance(emulators_data, dict):
        return

    for emu_name, emu_data in emulators_data.items():
        emulator_elem = ET.SubElement(parent_elem, "emulator", name=emu_name)

        if not isinstance(emu_data, dict):
            continue

        # Buscamos la sección de cores de forma segura
        cores_data = emu_data.get("cores", {})
        if not isinstance(cores_data, dict):
            continue

        for core_name, core_props in cores_data.items():
            # core_props puede contener 'default', 'incompatible_extensions' y 'options'
            core_attrs = _build_core_attributes(core_props)
            core_elem = ET.SubElement(emulator_elem, "core", **core_attrs)
            core_elem.text = core_name

def generate_es_systems(base_path: Path = _SYSTEMS_CONF_DIR, output_path: Path = ES_SYSTEMS_TMP):
    """
    Recorre la estructura de directorios YAML generada y reconstruye 
    el archivo es_systems.cfg original.
    """
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"Systems dir not found: {base_path}")

    if not os.path.isdir(base_path):
        raise NotADirectoryError(f"Systems dir isn't a directory: {base_path}")


    _logger.info("Begin generating %s", output_path)

    if output_path.exists() or output_path.is_symlink():
        output_path.unlink()

    if output_path != ES_SYSTEMS_CFG and \
    (ES_SYSTEMS_CFG.exists() or ES_SYSTEMS_CFG.is_symlink()):
        ES_SYSTEMS_CFG.unlink()

    base_dir: str = str(base_path)
    output_cfg_file: str = str(output_path)

    root = ET.Element("systemList")

    # Forzar la ruta a string para evitar falsos positivos de iteración en linters
    safe_base_dir = os.fspath(base_dir)
    #print(os.environ)
    for root_dir, _, files in os.walk(safe_base_dir):
        for file in files:
            if not file.endswith(".yaml") or file == "defaults.yml":
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
            #print(f"================ {ROMS}/{sys_name}")
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
    _logger.info("Successfully generated: %s", output_cfg_file)

    if output_path != ES_SYSTEMS_CFG:
        try:
            if ES_SYSTEMS_CFG.exists() or ES_SYSTEMS_CFG.is_symlink():
                ES_SYSTEMS_CFG.unlink()
            ES_SYSTEMS_CFG.symlink_to(output_path)
            _logger.info("Successfully linked: %s", ES_SYSTEMS_CFG)
        except FileNotFoundError as e:
            _logger.error(
                "Can't create symlink in %s: %s",
                ES_SYSTEMS_CFG.parent, e
            )
            raise

    _logger.info("=========")
