#!/usr/bin/env python3
"""
bios_classify.py — Clasifica archivos/carpetas de BIOS sueltos en carpetas
por EMULADOR/CORE, combinando tres fuentes de información:

  1. Los ficheros *_libretro.info de los cores de RetroArch instalados
     (mismo mecanismo que usa bios_check.py). Todo lo que coincide aquí
     va a:
         <destino>/libretro/<core>/

  2. El script "batocera-systems" del repo oficial de Batocera
     (batocera-linux/batocera.linux), que trae, por sistema, la lista
     "biosFiles" completa (todas las variantes/regiones, incluidas
     muchas que el .info de un core no declara, y ficheros usados por
     emuladores fuera de RetroArch). Cada entrada de biosFiles puede
     traer ya su propio "emulator"/"core" explícito (ej. algunos
     ficheros de Macintosh o Vectrex usan el core "mame" en vez del
     emulador por defecto del sistema); en ese caso se usa tal cual:
         <destino>/<emulator>/<core>/

  3. Cuando batocera-systems NO especifica emulator/core para una
     entrada (el caso normal: se asume "el emulador por defecto de ese
     sistema en Batocera"), se resuelve ese emulador/core por defecto
     consultando resources/systems_config/<fabricante>/<sistema>.yaml,
     que es donde de verdad vive esa información:
       - Se coge el PRIMER emulador definido en el YAML (el orden del
         propio fichero, ej. "libretro" antes que "ares").
       - Dentro de ese emulador, el core marcado con "default: true";
         si ninguno lo indica y solo hay un core, se usa ese; si hay
         varios sin marcar, se usa el primero y se avisa por si conviene
         revisarlo.
     Con esto, TODO acaba organizado por emulador/core (nunca por
     nombre de sistema): p. ej. "megadrive" con genesis_plus_gx marcado
     "default: true" en su YAML clasifica en:
         <destino>/libretro/genesis_plus_gx/
     Si un sistema de batocera-systems no tiene YAML correspondiente en
     systems_config (o no se puede resolver su emulador por defecto),
     cae como último recurso en:
         <destino>/_sin_emulador/<system_id>/
     y se avisa en el resumen para poder revisarlo o añadir un alias
     (ver más abajo).

  4. Lo que no coincide con ninguna fuente va a:
         <destino>/_other/

IMPORTANTE: este script debe colocarse en la MISMA carpeta que
bios_check.py, porque lo importa directamente para reutilizar su lógica
de lectura de los ficheros .info (parse_core_info, SYSTEMS_CONFIG_DIR,
load_yaml) y no duplicar código.

Alias de sistemas (opcional)
-----------------------------
Si algún id de sistema de batocera-systems no coincide exactamente con
la clave usada en resources/systems_config (p. ej. por diferencias de
nomenclatura), puedes crear, junto a este script, un fichero
"batocera_system_aliases.yaml" con el mapeo manual:

    # id_en_batocera-systems: clave_en_systems_config
    megadrive-msu: megadrive
    n64dd: n64

Descarga de batocera-systems
-----------------------------
Se descarga en tiempo de ejecución y se cachea en un fichero oculto
junto a este script (.batocera_systems_cache.py) para poder trabajar
sin red en ejecuciones posteriores. Usa --refresh-batocera para forzar
una descarga nueva, o --no-batocera para desactivar esta fuente.

Uso:
  bios_classify.py [origen] [destino] [opciones]

  origen  (por defecto: /home/manuel/Escritorio/bios)
  destino (por defecto: /home/manuel/Escritorio/bios_clasf)

Opciones:
  --dry-run           Solo muestra qué haría, sin copiar/mover nada.
  --move              Mueve en vez de copiar (si una BIOS es compartida
                       por varios destinos, el último recibe un "move" y
                       el resto copias, para no perder el original).
  --no-batocera       No usa batocera-systems, solo los cores de RetroArch.
  --refresh-batocera  Ignora la caché local y vuelve a descargar
                       batocera-systems desde GitHub.
  --batocera-url URL  URL alternativa de donde descargar batocera-systems.

Prioridad de clasificación por cada entrada de <origen> (archivo o
carpeta, se compara el NOMBRE, sin distinguir mayúsculas/minúsculas):
  1) ¿Coincide con algún firmwareN_path de algún core instalado?
     -> libretro/<core>/   (puede ir a varios cores si lo comparten)
  2) Si no, ¿coincide con algún fichero de biosFiles en batocera-systems?
     -> <emulator>/<core>/ (explícito, o resuelto vía systems_config)
  3) Si no coincide con nada -> _other/
"""
import argparse
import ast
import glob
import os
import shutil
import sys
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    import bios_check  # reutiliza parse_core_info, SYSTEMS_CONFIG_DIR, load_yaml
except ImportError:
    sys.stderr.write(
        "ERROR: no se encuentra bios_check.py. Este script debe estar en "
        "la misma carpeta que bios_check.py.\n"
    )
    sys.exit(2)

DEFAULT_SOURCE = "/home/manuel/Escritorio/bios"
DEFAULT_DEST = "/home/manuel/Escritorio/bios_clasf"
OTHER_DIRNAME = "_other"
LIBRETRO_DIRNAME = "libretro"
UNRESOLVED_DIRNAME = "_sin_emulador"

BATOCERA_SYSTEMS_URL = (
    "https://raw.githubusercontent.com/batocera-linux/batocera.linux/"
    "master/package/batocera/core/batocera-scripts/scripts/batocera-systems"
)
BATOCERA_SYSTEMS_CACHE = os.path.join(SCRIPT_DIR, ".batocera_systems_cache.py")
BATOCERA_SYSTEM_ALIASES_FILE = os.path.join(SCRIPT_DIR, "batocera_system_aliases.yaml")


def log(msg):
    print(msg)


# ---------------------------------------------------------------------------
# Fuente 1: cores de RetroArch instalados (igual que bios_check.py)
# ---------------------------------------------------------------------------

def discover_installed_cores():
    """Nombres de core (sin '_libretro.info') que están instalados."""
    if not os.path.isdir(bios_check.CORES_INFO_DIR):
        return []
    cores = []
    for fname in os.listdir(bios_check.CORES_INFO_DIR):
        if fname.endswith("_libretro.info"):
            cores.append(fname[: -len("_libretro.info")])
    return sorted(cores)


def build_name_to_cores_map(cores):
    """
    { nombre_en_minusculas: set(core, ...) }
    Incluye el nombre de archivo final de cada firmware y el primer
    componente de su ruta, por si el firmware vive en subcarpeta.
    """
    mapping = {}

    def add(name, core):
        if name:
            mapping.setdefault(name.lower(), set()).add(core)

    for core in cores:
        firmware = bios_check.parse_core_info(core)
        if not firmware:
            continue
        for fw in firmware:
            path = fw["path"].replace("\\", "/")
            add(os.path.basename(path), core)
            add(path.split("/")[0], core)

    return mapping


# ---------------------------------------------------------------------------
# Fuente 2: resources/systems_config/*/*.yaml -> emulador/core por defecto
# ---------------------------------------------------------------------------

def discover_system_default_emulator_core():
    """
    { system_key: (emulator, core) } leyendo
    resources/systems_config/<fabricante>/<sistema>.yaml

    Se toma el primer emulador definido en el YAML (su orden natural) y,
    dentro de él, el core marcado "default: true"; si ninguno lo indica
    y solo hay un core, se usa ese; si hay varios sin marcar, se usa el
    primero (best-effort) y se avisa al final.
    """
    result = {}
    ambiguous = []

    pattern = os.path.join(bios_check.SYSTEMS_CONFIG_DIR, "*", "*.yaml")
    for yaml_path in sorted(glob.glob(pattern)):
        try:
            raw = bios_check.load_yaml(yaml_path)
        except Exception as exc:
            log(f"[WARN] No se pudo parsear {yaml_path}: {exc}")
            continue
        if not raw:
            continue

        if len(raw) != 1:
            system_key = os.path.splitext(os.path.basename(yaml_path))[0]
            data = raw
        else:
            system_key = next(iter(raw))
            data = raw[system_key] or {}

        emulators = (data or {}).get("emulators") or {}
        if not emulators:
            continue

        emulator_name = next(iter(emulators))
        emulator_conf = emulators.get(emulator_name) or {}
        cores = emulator_conf.get("cores") or {}
        if not cores:
            continue

        default_core = None
        for core_name, core_conf in cores.items():
            if isinstance(core_conf, dict) and core_conf.get("default") is True:
                default_core = core_name
                break

        if default_core is None:
            default_core = next(iter(cores))
            if len(cores) > 1:
                ambiguous.append(system_key)

        result[system_key] = (emulator_name, default_core)

    if ambiguous:
        log(f"[AVISO] {len(ambiguous)} sistema(s) en systems_config con "
            f"varios cores para su emulador principal y ninguno marcado "
            f"'default: true' (se usó el primero definido, revisar si "
            f"conviene marcar el default explícitamente): "
            f"{', '.join(sorted(ambiguous))}")

    return result


def load_batocera_system_aliases():
    """{ id_en_batocera_systems: clave_en_systems_config }, opcional."""
    if not os.path.isfile(BATOCERA_SYSTEM_ALIASES_FILE):
        return {}
    try:
        data = bios_check.load_yaml(BATOCERA_SYSTEM_ALIASES_FILE) or {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception as exc:
        log(f"[AVISO] No se pudo leer {BATOCERA_SYSTEM_ALIASES_FILE}: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Fuente 3: batocera-systems (repo oficial de Batocera)
# ---------------------------------------------------------------------------

def fetch_batocera_systems_source(url, refresh=False):
    if not refresh and os.path.isfile(BATOCERA_SYSTEMS_CACHE):
        with open(BATOCERA_SYSTEMS_CACHE, "r", encoding="utf-8") as fh:
            return fh.read()

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bios_classify.py"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as exc:
        if os.path.isfile(BATOCERA_SYSTEMS_CACHE):
            log(f"[AVISO] No se pudo descargar batocera-systems ({exc}); "
                f"uso la copia en caché local.")
            with open(BATOCERA_SYSTEMS_CACHE, "r", encoding="utf-8") as fh:
                return fh.read()
        raise

    try:
        with open(BATOCERA_SYSTEMS_CACHE, "w", encoding="utf-8") as fh:
            fh.write(data)
    except OSError:
        pass  # sin permisos de escritura junto al script: seguimos sin cachear

    return data


def parse_batocera_systems_dict(source_code):
    """
    Extrae de forma SEGURA (sin ejecutar código, solo con ast.literal_eval)
    el diccionario 'systems' definido en el script batocera-systems.
    """
    tree = ast.parse(source_code)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "systems":
                    return ast.literal_eval(node.value)
    raise ValueError("No se encontró la variable 'systems' en el fichero descargado")


def format_dest(emulator, core):
    """
    Construye la ruta relativa de destino a partir de emulador y core.

    Para RetroArch (u otros emuladores con varios cores/modelos reales,
    ej. amiberry: A500, A1200, CD32...) el core aporta información y se
    mantiene: "<emulator>/<core>/".

    Para emuladores standalone donde el YAML solo declara un "core" con
    el mismo nombre que el propio emulador (ej. dolphin/dolphin,
    rpcs3/rpcs3, vita3k/vita3k, clk/clk, gsplus/gsplus...) esa carpeta
    extra no aporta nada, así que se colapsa a "<emulator>/".
    """
    if not emulator:
        return None
    if not core or core.lower() == emulator.lower():
        return emulator
    return f"{emulator}/{core}"


def build_name_to_dest_from_batocera(systems_dict, system_defaults, aliases):
    """
    { nombre_en_minusculas: set("emulator/core", ...) }

    "emulator/core" sale de la propia entrada de batocera-systems si la
    trae explícita, o si no, se resuelve vía system_defaults (a su vez
    obtenido de systems_config), aplicando antes el alias si existe.
    """
    mapping = {}
    unresolved_systems = set()

    def add(name, dest):
        if name:
            mapping.setdefault(name.lower(), set()).add(dest)

    for system_id, system in systems_dict.items():
        if not isinstance(system, dict):
            continue
        default_emulator = system.get("emulator")
        default_core = system.get("core")

        for entry in system.get("biosFiles", []) or []:
            file_path = entry.get("file")
            if not file_path:
                continue

            rel = file_path.replace("\\", "/")
            if rel.lower().startswith("bios/"):
                rel = rel[len("bios/"):]
            if not rel:
                continue

            basename = os.path.basename(rel)
            top_component = rel.split("/")[0]

            emulator = entry.get("emulator", default_emulator)
            core = entry.get("core", default_core)

            if emulator and core:
                dest = format_dest(emulator, core)
            else:
                lookup_key = aliases.get(system_id, system_id)
                resolved = system_defaults.get(lookup_key)
                if resolved:
                    dest = format_dest(resolved[0], resolved[1])
                else:
                    dest = f"{UNRESOLVED_DIRNAME}/{system_id}"
                    unresolved_systems.add(system_id)

            add(basename, dest)
            add(top_component, dest)

    if unresolved_systems:
        log(f"[AVISO] {len(unresolved_systems)} sistema(s) de "
            f"batocera-systems sin emulador/core resuelto vía "
            f"systems_config (agrupados por sistema en "
            f"'{UNRESOLVED_DIRNAME}/'; considera añadir un alias en "
            f"{os.path.basename(BATOCERA_SYSTEM_ALIASES_FILE)} si el id "
            f"no coincide con el de tu systems_config): "
            f"{', '.join(sorted(unresolved_systems))}")

    return mapping


# ---------------------------------------------------------------------------
# Copiado / movimiento de entradas
# ---------------------------------------------------------------------------

def ensure_dir(path, dry_run):
    if not dry_run:
        os.makedirs(path, exist_ok=True)


def place_entry(src, dst, dry_run, move, is_last_use):
    if dry_run:
        return
    is_dir = os.path.isdir(src)
    if os.path.exists(dst):
        if is_dir:
            shutil.rmtree(dst)
        else:
            os.remove(dst)
    if move and is_last_use:
        shutil.move(src, dst)
    elif is_dir:
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def place_in_destinations(name, src_path, dest_labels, dest_root, dry_run, move, log_prefix):
    """dest_labels: iterable de rutas relativas tipo 'libretro/genesis_plus_gx'."""
    labels_sorted = sorted(dest_labels)
    for i, label in enumerate(labels_sorted):
        dest_dir = os.path.join(dest_root, *label.split("/"))
        ensure_dir(dest_dir, dry_run)
        dest_path = os.path.join(dest_dir, name)
        is_last_use = i == len(labels_sorted) - 1
        extra = ""
        if len(labels_sorted) > 1:
            others = ", ".join(l for l in labels_sorted if l != label)
            extra = f"   (compartido con: {others})"
        log(f"[{log_prefix}]  {name}  ->  {label}/{extra}")
        place_entry(src_path, dest_path, dry_run, move, is_last_use=is_last_use)


# ---------------------------------------------------------------------------
# Clasificación principal
# ---------------------------------------------------------------------------

def classify(source, dest, dry_run=False, move=False, use_batocera=True,
             refresh_batocera=False, batocera_url=BATOCERA_SYSTEMS_URL):
    cores = discover_installed_cores()
    if not cores:
        log(f"[ERROR] No se encontraron cores instalados en "
            f"{bios_check.CORES_INFO_DIR}")
        return 2
    libretro_map = build_name_to_cores_map(cores)
    log(f"RetroArch: {sum(1 for c in cores if bios_check.parse_core_info(c))} "
        f"de {len(cores)} cores instalados declaran firmware.")

    batocera_map = {}
    if use_batocera:
        try:
            src_code = fetch_batocera_systems_source(batocera_url, refresh=refresh_batocera)
            systems_dict = parse_batocera_systems_dict(src_code)
            system_defaults = discover_system_default_emulator_core()
            aliases = load_batocera_system_aliases()
            batocera_map = build_name_to_dest_from_batocera(systems_dict, system_defaults, aliases)
            log(f"batocera-systems: {len(systems_dict)} sistemas, "
                f"{len(system_defaults)} resueltos vía systems_config, "
                f"{len(batocera_map)} nombres de fichero/carpeta indexados.")
        except Exception as exc:
            log(f"[AVISO] No se pudo usar batocera-systems ({exc}); "
                f"se continúa solo con los cores de RetroArch.")

    if not os.path.isdir(source):
        log(f"[ERROR] La carpeta de origen no existe: {source}")
        return 2

    entries = sorted(os.listdir(source))
    if not entries:
        log(f"[AVISO] {source} está vacía, nada que clasificar.")
        return 0

    count_libretro = 0
    count_batocera = 0
    count_other = 0

    for name in entries:
        src_path = os.path.join(source, name)
        key = name.lower()

        matched_cores = libretro_map.get(key)
        if matched_cores:
            labels = {f"{LIBRETRO_DIRNAME}/{core}" for core in matched_cores}
            place_in_destinations(name, src_path, labels, dest, dry_run, move, "LIBRETRO")
            count_libretro += 1
            continue

        matched_batocera = batocera_map.get(key) if use_batocera else None
        if matched_batocera:
            place_in_destinations(name, src_path, matched_batocera, dest, dry_run, move, "BATOCERA")
            count_batocera += 1
            continue

        dest_dir = os.path.join(dest, OTHER_DIRNAME)
        ensure_dir(dest_dir, dry_run)
        dest_path = os.path.join(dest_dir, name)
        log(f"[OTHER]    {name}  ->  {OTHER_DIRNAME}/")
        place_entry(src_path, dest_path, dry_run, move, is_last_use=True)
        count_other += 1

    log("\n" + "=" * 60)
    log(f"Resumen: {count_libretro} por core de RetroArch, "
        f"{count_batocera} por batocera-systems, "
        f"{count_other} sin identificar (en {OTHER_DIRNAME}/).")
    if dry_run:
        log("(--dry-run: no se ha copiado ni movido nada realmente)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Clasifica BIOS sueltas por emulador/core (RetroArch + batocera-systems)."
    )
    parser.add_argument("source", nargs="?", default=DEFAULT_SOURCE,
                         help=f"Carpeta origen (por defecto: {DEFAULT_SOURCE})")
    parser.add_argument("dest", nargs="?", default=DEFAULT_DEST,
                         help=f"Carpeta destino (por defecto: {DEFAULT_DEST})")
    parser.add_argument("--dry-run", action="store_true",
                         help="Solo muestra qué haría, sin copiar/mover nada.")
    parser.add_argument("--move", action="store_true",
                         help="Mueve en vez de copiar (compartidas: move en el "
                              "último destino, copia en el resto).")
    parser.add_argument("--no-batocera", action="store_true",
                         help="No usa batocera-systems, solo cores de RetroArch.")
    parser.add_argument("--refresh-batocera", action="store_true",
                         help="Ignora la caché local y vuelve a descargar "
                              "batocera-systems desde GitHub.")
    parser.add_argument("--batocera-url", default=BATOCERA_SYSTEMS_URL,
                         help="URL alternativa para descargar batocera-systems.")
    args = parser.parse_args()
    return classify(
        args.source, args.dest,
        dry_run=args.dry_run,
        move=args.move,
        use_batocera=not args.no_batocera,
        refresh_batocera=args.refresh_batocera,
        batocera_url=args.batocera_url,
    )


if __name__ == "__main__":
    sys.exit(main())