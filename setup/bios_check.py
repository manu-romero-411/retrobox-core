#!/usr/bin/env python3
"""
bios_check.py — Comprueba que las BIOS/firmware requeridas por los cores de
RetroArch instalados están presentes en bios/<sistema-batocera>/.

Fuentes de información:
  - resources/systems_config/<fabricante>/<sistema>.yaml
        Define qué cores de libretro usa cada sistema.
  - emulators/retroarch/app/share/retroarch/cores/<core>_libretro.info
        Define qué ficheros de firmware necesita cada core (firmwareN_path,
        firmwareN_opt, firmwareN_desc). Se usa como base cuando el core no
        tiene entrada en el override.
  - setup/bios_core_overrides.yaml (opcional)
        Lista, a mano, exactamente qué ficheros hacen falta para un
        (core, sistema) dado. Si un core aparece aquí para un sistema, esa
        lista SUSTITUYE por completo lo derivado del .info para ese
        sistema — todo lo que pongas se trata como necesario, sin concepto
        de "opcional". Útil tanto para cores que sirven a varios sistemas
        a la vez (p.ej. genesis_plus_gx: Mega Drive + Master System + Game
        Gear + Mega-CD, cuyo .info mezcla toda la firmware) como para
        cores con ficheros que ni siquiera aparecen en su .info (p.ej.
        pcsx2 necesita también patches.zip, que no está declarado ahí).

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

FOLDER_HINT_RE = re.compile(r"\bfolder\b|\bdirectory\b|\bdirectorio\b|\bcarpeta\b", re.I)


def guess_kind(path, desc):
    """
    Algunos cores declaran como 'firmware' lo que en realidad es una carpeta
    entera (p.ej. pcsx2: firmware*_desc = "'pcsx2/bios' folder"). El .info
    no tiene un campo estructurado para esto, así que lo detectamos por
    texto en la descripción (o porque la ruta termina en "/").
    """
    if FOLDER_HINT_RE.search(desc or ""):
        return "dir"
    if path.endswith("/"):
        return "dir"
    return "file"


def log(msg):
    print(msg)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_overrides():
    """
    Returns: core -> system -> list[str filename]

    Formato plano, idéntico para cualquier core: si (core, system) aparece
    aquí, esa lista sustituye por completo lo que se comprobaría para ese
    core en ese sistema (tanto si el core es de un solo sistema, como
    pcsx2, como si es multi-sistema, como genesis_plus_gx). No hay
    "opcional": todo lo listado se trata como necesario.
    """
    if not os.path.isfile(OVERRIDES_FILE):
        return {}
    data = load_yaml(OVERRIDES_FILE) or {}
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
    Returns list of firmware dicts [{index, path, desc, optional, kind}],
    or None if the .info file doesn't exist (core not built/installed).
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
        desc = kv.get(f"firmware{i}_desc", "")
        firmware.append(
            {
                "index": i,
                "path": path,
                "desc": desc,
                "optional": kv.get(f"firmware{i}_opt", "false").lower() == "true",
                "kind": guess_kind(path, desc),
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
    Decide qué ficheros hacen falta para este (core, system). Devuelve
    (wanted_list, status) donde status es uno de:
      'override'       -> había entrada en bios_core_overrides.yaml, se usa
                           tal cual (sustituye lo derivado del .info).
      'single-system'   -> sin override, pero el core solo lo usa este
                           sistema, así que se usan todas sus firmware.
      'ambiguous'       -> sin override y el core lo usan varios sistemas;
                           best-effort mostrando todas las firmware conocidas.
    all_firmware puede ser None si el core no está instalado (no existe su
    .info); en ese caso solo puede resolverse vía override.
    """
    core_overrides = overrides.get(core_name, {})

    if system_key in core_overrides:
        wanted_paths = core_overrides[system_key]
        by_path = {fw["path"]: fw for fw in (all_firmware or [])}
        wanted = []
        for p in wanted_paths:
            if p in by_path:
                wanted.append(by_path[p])
            else:
                # El override menciona un fichero que no aparece en el
                # .info del core (o el core ni está instalado): lo
                # comprobamos igualmente como entrada "manual".
                wanted.append(
                    {
                        "index": -1,
                        "path": p,
                        "desc": "",
                        "optional": False,
                        "kind": guess_kind(p, ""),
                    }
                )
        return wanted, "override"

    if all_firmware is None:
        return [], "single-system"

    used_by = core_usage.get(core_name, {system_key})
    if len(used_by) <= 1:
        return all_firmware, "single-system"

    return all_firmware, "ambiguous"


def check_bios_path(system_key, entry):
    """
    Comprueba la entrada (fichero o carpeta) bajo bios/<system_key>/.
    Devuelve una tupla (status, detail):
      status: 'ok_file' | 'ok_dir' | 'empty_dir' | 'missing'
      detail: nº de ficheros dentro, si es carpeta; si no, None.
    Trata una carpeta vacía como si faltara: una carpeta 'bios' vacía no
    sirve de nada, y así evitamos falsos "OK".
    """
    full_path = os.path.join(BIOS_DIR, system_key, entry["path"])
    kind = entry.get("kind") or "file"

    if kind == "dir":
        if not os.path.isdir(full_path):
            return "missing", None
        try:
            contents = [f for f in os.listdir(full_path) if not f.startswith(".")]
        except OSError:
            contents = []
        if not contents:
            return "empty_dir", 0
        return "ok_dir", len(contents)

    # kind == "file": si por lo que sea existe como carpeta en vez de
    # fichero, lo tratamos igualmente como no válido (missing), en vez de
    # reventar más adelante.
    if os.path.isfile(full_path):
        return "ok_file", None
    return "missing", None


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
    ambiguous_cores = set()
    cores_not_built = set()

    for system_key in sorted(target_systems):
        info = target_systems[system_key]
        if not info["cores"]:
            continue

        printed_header = False

        def ensure_header():
            nonlocal printed_header
            if not printed_header:
                log(f"\n=== {info['fullname']} ({system_key}) ===")
                printed_header = True

        for core in info["cores"]:
            all_firmware = parse_core_info(core)

            if all_firmware is None and core not in overrides:
                cores_not_built.add(core)
                ensure_header()
                log(f"  [SKIP] core '{core}' no está instalado/compilado "
                    f"(no existe {core}_libretro.info)")
                continue

            wanted, status = resolve_wanted_firmware(
                core, system_key, all_firmware, core_usage, overrides
            )

            if not wanted:
                continue

            ensure_header()

            if all_firmware is None:
                log(f"  [NOTA] core '{core}' no está instalado, pero tiene "
                    f"override definido; se comprueba igualmente.")

            if status == "ambiguous":
                ambiguous_cores.add(core)
                log(f"  [WARN] core '{core}' es usado por varios sistemas "
                    f"({', '.join(sorted(core_usage[core]))}) y no tiene "
                    f"entrada en {os.path.basename(OVERRIDES_FILE)}. "
                    f"Mostrando todas las firmware conocidas (puede incluir "
                    f"falsos positivos de otros sistemas).")

            for fw in wanted:
                status_check, detail = check_bios_path(system_key, fw)

                if status_check == "ok_file":
                    log(f"  [OK]      {core}: {fw['path']}")
                    continue
                if status_check == "ok_dir":
                    shown = fw['path'] if fw['path'].endswith('/') else fw['path'] + '/'
                    log(f"  [OK]      {core}: {shown} (carpeta, {detail} ficheros)")
                    continue

                if status_check == "empty_dir":
                    note = "carpeta vacía"
                else:
                    note = "carpeta ausente" if fw.get("kind") == "dir" else "ausente"

                suffix = f" — {fw['desc']}" if fw.get("desc") else ""

                # El único caso en que algo puede quedar como "opcional" es
                # cuando NO hay override y se usa tal cual lo que declara el
                # .info del core (firmwareN_opt). En cuanto hay override
                # para ese (core, system), todo es requerido.
                if status != "override" and fw.get("optional"):
                    log(f"  [MISSING] {core}: {fw['path']} ({note}, opcional){suffix}")
                else:
                    missing_required += 1
                    log(f"  [MISSING] {core}: {fw['path']} ({note}, REQUERIDA){suffix}")

    log("\n" + "=" * 60)
    log(f"Resumen: {missing_required} BIOS requeridas ausentes.")
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