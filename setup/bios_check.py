#!/usr/bin/env python3
"""
bios_check.py — Comprueba que las BIOS/firmware requeridas por los cores de
RetroArch instalados están presentes en bios/<sistema-batocera>/.

Fuentes de información:
  - resources/systems_config/<fabricante>/<sistema>.yaml
        Define qué cores de libretro usa cada sistema.
  - emulators/retroarch/app/share/retroarch/cores/<core>_libretro.info
        Define qué ficheros de firmware necesita cada core (firmwareN_path,
        firmwareN_opt, firmwareN_desc).
  - setup/bios_core_overrides.yaml (opcional)
        Para cores que sirven a varios sistemas a la vez (p.ej.
        genesis_plus_gx: Mega Drive + Master System + Game Gear + Mega-CD),
        el .info trae TODAS las firmware mezcladas. Este fichero permite
        indicar a mano qué ficheros de firmware corresponden a cada sistema
        para ese core. Si un core es ambiguo (usado por >1 sistema) y no
        tiene entrada aquí, se avisa y se hace un best-effort.

Uso:
  bios_check.py                  # comprueba todos los sistemas
  bios_check.py megadrive snes   # comprueba solo esos sistemas
  bios_check.py --list-ambiguous # lista cores multi-sistema sin override
"""
import os
import re
import sys
import glob

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "ERROR: falta el módulo 'pyyaml' (pip install pyyaml / "
        "python3-yaml).\n"
    )
    sys.exit(2)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEMS_CONFIG_DIR = os.path.join(ROOT_DIR, "resources", "systems_config")
CORES_INFO_DIR = os.path.join(
    ROOT_DIR, "emulators", "retroarch", "app", "share", "retroarch", "cores"
)
BIOS_DIR = os.path.join(ROOT_DIR, "bios")
OVERRIDES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bios_core_overrides.yaml"
)

INFO_LINE_RE = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"?([^"\n]*)"?\s*$')


def log(msg):
    print(msg)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_overrides():
    if not os.path.isfile(OVERRIDES_FILE):
        return {}
    data = load_yaml(OVERRIDES_FILE) or {}
    # Normalize: core -> system -> list[str]
    return {
        core: {system: list(files or []) for system, files in systems.items()}
        for core, systems in data.items()
    }


def discover_systems():
    """
    Returns { system_key: {"fullname": ..., "manufacturer": ..., "cores": [core_name, ...]} }
    Only libretro cores are considered.
    """
    systems = {}
    pattern = os.path.join(SYSTEMS_CONFIG_DIR, "*", "*.yaml")
    for yaml_path in sorted(glob.glob(pattern)):
        file_stem = os.path.splitext(os.path.basename(yaml_path))[0]
        try:
            raw = load_yaml(yaml_path)
        except yaml.YAMLError as exc:
            log(f"[WARN] No se pudo parsear {yaml_path}: {exc}")
            continue

        if not raw:
            continue

        # El YAML trae el id del sistema como clave raíz, p.ej.:
        #   megadrive:
        #     fullname: Mega Drive
        #     ...
        # Usamos esa clave (no el nombre de fichero) como system_key, por
        # si alguna vez no coinciden.
        if len(raw) != 1:
            log(f"[WARN] {yaml_path}: se esperaba una única clave raíz "
                f"(el id del sistema), se encontraron {len(raw)}. Se usa "
                f"el nombre de fichero '{file_stem}'.")
            system_key = file_stem
            data = raw
        else:
            system_key = next(iter(raw))
            data = raw[system_key] or {}

        emulators = (data or {}).get("emulators") or {}
        libretro = emulators.get("libretro") or {}
        cores = list((libretro.get("cores") or {}).keys())

        systems[system_key] = {
            "fullname": data.get("fullname", system_key),
            "manufacturer": data.get("manufacturer", ""),
            "cores": cores,
            "yaml_path": yaml_path,
        }
    return systems


def parse_core_info(core_name):
    """
    Returns list of firmware dicts [{index, path, desc, optional}], or None
    if the .info file doesn't exist (core not built/installed).
    """
    info_path = os.path.join(CORES_INFO_DIR, f"{core_name}_libretro.info")
    if not os.path.isfile(info_path):
        return None

    kv = {}
    with open(info_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = INFO_LINE_RE.match(line)
            if m:
                kv[m.group(1)] = m.group(2)

    try:
        count = int(kv.get("firmware_count", "0") or "0")
    except ValueError:
        count = 0

    firmware = []
    for i in range(count):
        path = kv.get(f"firmware{i}_path")
        if not path:
            continue
        firmware.append(
            {
                "index": i,
                "path": path,
                "desc": kv.get(f"firmware{i}_desc", ""),
                "optional": kv.get(f"firmware{i}_opt", "false").lower() == "true",
            }
        )
    return firmware


def build_core_usage(systems):
    """core_name -> set(system_key, ...)"""
    usage = {}
    for system_key, info in systems.items():
        for core in info["cores"]:
            usage.setdefault(core, set()).add(system_key)
    return usage


def resolve_wanted_firmware(core_name, system_key, all_firmware, core_usage, overrides):
    """
    Decide qué entradas de firmware (de all_firmware) aplican a este sistema
    para este core. Devuelve (wanted_list, status) donde status es uno de:
    'single-system', 'override', 'ambiguous'.
    """
    used_by = core_usage.get(core_name, {system_key})

    if len(used_by) <= 1:
        return all_firmware, "single-system"

    core_overrides = overrides.get(core_name, {})
    if system_key in core_overrides:
        wanted_paths = set(core_overrides[system_key])
        by_path = {fw["path"]: fw for fw in all_firmware}
        wanted = []
        for p in wanted_paths:
            if p in by_path:
                wanted.append(by_path[p])
            else:
                # El override menciona un fichero que ya no aparece en el
                # .info actual del core (puede haber cambiado de versión).
                wanted.append(
                    {"index": -1, "path": p, "desc": "(definido en override)", "optional": False}
                )
        return wanted, "override"

    return all_firmware, "ambiguous"


def check_bios_file(system_key, filename):
    return os.path.isfile(os.path.join(BIOS_DIR, system_key, filename))


def run_check(system_filter=None):
    systems = discover_systems()
    if not systems:
        log(f"[ERROR] No se encontraron sistemas en {SYSTEMS_CONFIG_DIR}")
        return 2

    core_usage = build_core_usage(systems)
    overrides = load_overrides()

    if system_filter:
        unknown = [s for s in system_filter if s not in systems]
        for s in unknown:
            log(f"[WARN] Sistema desconocido, se ignora: {s}")
        target_systems = {k: v for k, v in systems.items() if k in system_filter}
    else:
        target_systems = systems

    missing_required = 0
    missing_optional = 0
    ambiguous_cores = set()
    cores_not_built = set()

    for system_key in sorted(target_systems):
        info = target_systems[system_key]
        if not info["cores"]:
            continue

        log(f"\n=== {info['fullname']} ({system_key}) ===")

        for core in info["cores"]:
            all_firmware = parse_core_info(core)
            if all_firmware is None:
                cores_not_built.add(core)
                log(f"  [SKIP] core '{core}' no está instalado/compilado "
                    f"(no existe {core}_libretro.info)")
                continue

            if not all_firmware:
                continue  # este core no necesita firmware

            wanted, status = resolve_wanted_firmware(
                core, system_key, all_firmware, core_usage, overrides
            )

            if status == "ambiguous":
                ambiguous_cores.add(core)
                log(f"  [WARN] core '{core}' es usado por varios sistemas "
                    f"({', '.join(sorted(core_usage[core]))}) y no tiene "
                    f"entrada en {os.path.basename(OVERRIDES_FILE)}. "
                    f"Mostrando todas las firmware conocidas (puede incluir "
                    f"falsos positivos de otros sistemas).")

            for fw in wanted:
                exists = check_bios_file(system_key, fw["path"])
                if exists:
                    log(f"  [OK]      {core}: {fw['path']}")
                    continue
                if fw["optional"]:
                    missing_optional += 1
                    log(f"  [MISSING] {core}: {fw['path']} (opcional) — {fw['desc']}")
                else:
                    missing_required += 1
                    log(f"  [MISSING] {core}: {fw['path']} (REQUERIDA) — {fw['desc']}")

    log("\n" + "=" * 60)
    log(f"Resumen: {missing_required} BIOS requeridas ausentes, "
        f"{missing_optional} opcionales ausentes.")
    if ambiguous_cores:
        log(f"Cores ambiguos sin override ({len(ambiguous_cores)}): "
            f"{', '.join(sorted(ambiguous_cores))}")
        log(f"  -> añade una entrada para cada uno en "
            f"setup/bios_core_overrides.yaml para resultados exactos.")
    if cores_not_built:
        log(f"Cores no instalados ({len(cores_not_built)}): "
            f"{', '.join(sorted(cores_not_built))}")

    return 1 if missing_required else 0


def list_ambiguous():
    systems = discover_systems()
    core_usage = build_core_usage(systems)
    overrides = load_overrides()
    multi = {c: s for c, s in core_usage.items() if len(s) > 1}
    if not multi:
        log("No hay cores usados por más de un sistema.")
        return 0
    for core, sys_set in sorted(multi.items()):
        has_override = core in overrides
        marker = "OK (con override)" if has_override else "SIN OVERRIDE"
        log(f"{core}: {', '.join(sorted(sys_set))}  [{marker}]")
    return 0


def main(argv):
    if argv and argv[0] == "--list-ambiguous":
        return list_ambiguous()
    return run_check(system_filter=argv or None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
