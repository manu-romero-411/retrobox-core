"""
This submodule regenerates es_features.cfg based on YAML configuration files.
"""
import logging
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
import yaml
from yaml.scanner import ScannerError
from yaml.parser import ParserError

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

_logger = logging.getLogger(__name__)

from runtime.retrobox_paths import _ES_FEATURES_DIR, ES_FEATURES_CFG

ROOTDIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOTDIR))

def build_features_elements(parent_elem, data_dict):
    features = data_dict.get('features')
    if features:
        if isinstance(features, list):
            parent_elem.set('features', ", ".join(map(str, features)))
        else:
            parent_elem.set('features', str(features))

    shared_features = data_dict.get('sharedFeatures')
    if shared_features:
        for sf in shared_features:
            sf_elem = ET.SubElement(parent_elem, 'sharedFeature')
            sf_elem.set('value', str(sf))

    groups = data_dict.get('groups')
    if groups and isinstance(groups, dict):
        for group_name, group_content in groups.items():
            if not isinstance(group_content, dict):
                continue
            
            submenus = group_content.get('submenus', {})
            for submenu_name, items in submenus.items():
                if isinstance(items, list):
                    for item in items:
                        feat_elem = ET.SubElement(parent_elem, 'feature')
                        if group_name != 'GENERAL':
                            feat_elem.set('group', str(group_name))
                        if submenu_name != 'NONE':
                            feat_elem.set('submenu', str(submenu_name))
                        for k, v in item.items():
                            if k != 'choices' and v is not None:
                                feat_elem.set(str(k), str(v))
                        choices = item.get('choices')
                        if choices and isinstance(choices, list):
                            for choice in choices:
                                choice_elem = ET.SubElement(feat_elem, 'choice')
                                for ck, cv in choice.items():
                                    if cv is not None:
                                        choice_elem.set(str(ck), str(cv))

            items = group_content.get('items', [])
            if isinstance(items, list):
                for item in items:
                    feat_elem = ET.SubElement(parent_elem, 'feature')
                    if group_name != 'GENERAL':
                        feat_elem.set('group', str(group_name))
                    for k, v in item.items():
                        if k != 'choices' and v is not None:
                            feat_elem.set(str(k), str(v))
                    choices = item.get('choices')
                    if choices and isinstance(choices, list):
                        for choice in choices:
                            choice_elem = ET.SubElement(feat_elem, 'choice')
                            for ck, cv in choice.items():
                                if cv is not None:
                                    choice_elem.set(str(ck), str(cv))

def build_system_elements(parent_elem, systems_list):
    if not systems_list or not isinstance(systems_list, list):
        return
    systems_container = ET.SubElement(parent_elem, 'systems')
    for sys_data in systems_list:
        sys_elem = ET.SubElement(systems_container, 'system')
        for k, v in sys_data.items():
            if k not in ('features', 'groups') and v is not None:
                sys_elem.set(str(k), str(v))
        build_features_elements(sys_elem, sys_data)

def generate_es_features(yaml_dir: Path = _ES_FEATURES_DIR, output_cfg: Path = ES_FEATURES_CFG):
    """
    entrypoint to the es_features.cfg generator
    """
    _logger.info("Start generating: %s", output_cfg)
    root = ET.Element('features')

    yaml_files = sorted(list(yaml_dir.glob('*.yaml')))

    emulator_data_map = {}
    cores_data_map = {}
    global_config_data = None

    for yfile in yaml_files:
        try:
            with open(yfile, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data or not isinstance(data, dict):
                    continue

                emu_name = data.get('emulator_name')

                # Detectar el fichero especial global
                if emu_name == '_global_config':
                    global_config_data = data
                    continue

                core_name = data.get('core_name')

                if core_name:
                    if emu_name not in cores_data_map:
                        cores_data_map[emu_name] = []
                    cores_data_map[emu_name].append(data)
                else:
                    emulator_data_map[emu_name] = data
        except (ScannerError, ParserError) as e:
            _logger.error("Error parsing YAML file %s: %s", yfile.name, e)

    # 1. Reconstruir <sharedFeatures> y <globalFeatures> si existe el fichero global
    if global_config_data:
        groups = global_config_data.get('groups')
        if groups:
            shared_elem = ET.SubElement(root, 'sharedFeatures')
            build_features_elements(root, global_config_data)
            # Reorganizamos para mover los elementos feature dentro de sharedFeatures
            root.remove(shared_elem)
            for child in list(root):
                if child.tag == 'feature':
                    root.remove(child)
                    shared_elem.append(child)
            root.insert(0, shared_elem)

        shared_feats_list = global_config_data.get('sharedFeatures')
        if shared_feats_list:
            global_feats_elem = ET.SubElement(root, 'globalFeatures')
            for sf in shared_feats_list:
                sf_elem = ET.SubElement(global_feats_elem, 'sharedFeature')
                sf_elem.set('value', str(sf))

    # 2. Reconstruir emuladores y cores
    for emu_name, emu_data in emulator_data_map.items():
        emu_elem = ET.SubElement(root, 'emulator')
        emu_elem.set('name', str(emu_name))

        for k, v in emu_data.items():
            if k not in (
                'emulator_name',
                'features',
                'sharedFeatures',
                'systems',
                'groups'
            ) and v is not None:
                emu_elem.set(str(k), str(v))

        build_features_elements(emu_elem, emu_data)

        systems = emu_data.get('systems')
        if systems:
            build_system_elements(emu_elem, systems)

        if emu_name in cores_data_map:
            cores_container = ET.SubElement(emu_elem, 'cores')
            for core_data in cores_data_map[emu_name]:
                core_elem = ET.SubElement(cores_container, 'core')
                core_elem.set('name', str(core_data.get('core_name')))

                for k, v in core_data.items():
                    if k not in (
                        'emulator_name',
                        'core_name',
                        'features',
                        'sharedFeatures',
                        'systems',
                        'groups'
                    ) and v is not None:
                        core_elem.set(str(k), str(v))

                build_features_elements(core_elem, core_data)

                core_systems = core_data.get('systems')
                if core_systems:
                    build_system_elements(core_elem, core_systems)

    # Generación y formateo final del XML
    xml_string = ET.tostring(root, encoding='utf-8')
    parsed_dom = minidom.parseString(xml_string)
    pretty_xml = parsed_dom.toprettyxml(indent="  ", encoding="utf-8")

    lines = [line for line in pretty_xml.decode('utf-8').splitlines() if line.strip()]
    final_xml = "\n".join(lines)

    output_cfg.parent.mkdir(parents=True, exist_ok=True)
    with open(output_cfg, 'w', encoding='utf-8') as f:
        f.write(final_xml + "\n")

    _logger.info("Successfully regenerated: %s", output_cfg)
