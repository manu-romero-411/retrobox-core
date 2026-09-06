#!/usr/bin/env python3
"""
bios_fetch.py — Descarga BIOS/firmware de Batocera desde el repositorio
RetroBIOS (https://github.com/Abdess/retrobios), sistema por sistema y
archivo por archivo, sin clonar el repo completo.

Fuentes de información (se descargan de raw.githubusercontent.com y se
cachean en setup/.cache/retrobios/):

  - platforms/batocera.yml
        Manifiesto oficial de RetroBIOS para Batocera. Por cada sistema
        (clave = native_id, el mismo nombre de carpeta que usamos en
        resources/systems_config, p.ej. "psx", "dreamcast", "megadrive-msu")
        lista los ficheros requeridos con su ruta de destino relativa a
        bios/ (ya incluye subcarpeta cuando aplica, p.ej. "dc/dc_boot.bin",
        "neocd/neocd_f.rom") y su md5.

  - install/batocera.json
        Manifiesto de instalación "full pack" de RetroBIOS para Batocera:
        lista plana de todos los ficheros con su "dest" (mismo valor que
        "destination" en platforms/batocera.yml), su "repo_path" (ruta real
        del fichero dentro del repo RetroBIOS, usada para construir la URL
        de descarga) y sus hashes (sha1/sha256) + tamaño.

Se cruzan ambos por el campo dest/destination (es único en todo el
manifiesto de Batocera, sin colisiones) para obtener, por cada fichero de
un sistema: destino local, repo_path de origen y hash para verificar.

Uso:
  bios_fetch.py --list                     # lista sistemas disponibles
  bios_fetch.py psx gba                    # descarga BIOS de esos sistemas
  bios_fetch.py --dry-run dreamcast        # simula, no descarga
  bios_fetch.py --all                      # descarga todo (~1.2 GB)
  bios_fetch.py --refresh psx              # fuerza refresco del manifiesto
  bios_fetch.py --force psx                # redescarga aunque ya esté OK
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "ERROR: falta el módulo 'pyyaml' (pip install pyyaml / "
        "python3-yaml).\n"
    )
    sys.exit(2)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIOS_DIR = os.path.join(ROOT_DIR, "bios")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "retrobios")
PLATFORM_MANIFEST_URL = "https://raw.githubusercontent.com/Abdess/retrobios/main/platforms/batocera.yml"
INSTALL_MANIFEST_URL = "https://raw.githubusercontent.com/Abdess/retrobios/main/install/batocera.json"
RAW_BASE_URL = "https://raw.githubusercontent.com/Abdess/retrobios/main/"

PLATFORM_MANIFEST_CACHE = os.path.join(CACHE_DIR, "platforms_batocera.yml")
INSTALL_MANIFEST_CACHE = os.path.join(CACHE_DIR, "install_batocera.json")
MANIFEST_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 días

USER_AGENT = "retrobox-bios-fetch/1.0 (+https://github.com/Abdess/retrobios)"


def log(msg):
    print(msg)


def log_warn(msg):
    print(f"[WARN] {msg}")


def log_err(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _cache_is_fresh(path):
    if not os.path.isfile(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < MANIFEST_MAX_AGE_SECONDS


def ensure_manifests(force_refresh=False):
    """
    Descarga (o reutiliza de caché) los dos manifiestos de RetroBIOS.
    Devuelve (platform_manifest_path, install_manifest_path).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    for url, cache_path, label in (
        (PLATFORM_MANIFEST_URL, PLATFORM_MANIFEST_CACHE, "platforms/batocera.yml"),
        (INSTALL_MANIFEST_URL, INSTALL_MANIFEST_CACHE, "install/batocera.json"),
    ):
        if not force_refresh and _cache_is_fresh(cache_path):
            continue
        log(f"Descargando manifiesto de RetroBIOS: {label}...")
        try:
            data = _http_get(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            if os.path.isfile(cache_path):
                log_warn(
                    f"No se pudo refrescar {label} ({exc}); se usa la copia "
                    f"en caché (puede estar desactualizada)."
                )
                continue
            log_err(f"No se pudo descargar {label}: {exc}")
            sys.exit(2)
        with open(cache_path, "wb") as fh:
            fh.write(data)

    return PLATFORM_MANIFEST_CACHE, INSTALL_MANIFEST_CACHE


def load_platform_manifest(path):
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_install_manifest(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh) or {}


def build_dest_index(install_manifest):
    """dest -> {repo_path, sha1, sha256, size}"""
    index = {}
    for entry in install_manifest.get("files", []):
        index[entry["dest"]] = entry
    return index


def build_system_registry(platform_manifest):
    """
    native_id -> {yaml_key, name, files: [{destination, md5, required}]}
    """
    registry = {}
    for yaml_key, sysdef in (platform_manifest.get("systems") or {}).items():
        native_id = sysdef.get("native_id", yaml_key)
        registry[native_id] = {
            "yaml_key": yaml_key,
            "name": sysdef.get("name", native_id),
            "files": sysdef.get("files") or [],
        }
    return registry


def resolve_system_files(native_id, registry, dest_index):
    """
    Devuelve (system_info, resolved, unresolved) para un native_id dado.
    resolved: lista de dicts {destination, md5, repo_path, sha1, size}
    unresolved: lista de destinations que no se encontraron en el install
                manifest (caso raro, se avisa y se omite).
    """
    system_info = registry.get(native_id)
    if not system_info:
        return None, [], []

    resolved = []
    unresolved = []
    seen = set()
    for f in system_info["files"]:
        dest = f["destination"]
        if dest in seen:
            continue
        seen.add(dest)
        entry = dest_index.get(dest)
        if not entry:
            unresolved.append(dest)
            continue
        resolved.append(
            {
                "destination": dest,
                "md5": f.get("md5"),
                "repo_path": entry["repo_path"],
                "sha1": entry.get("sha1"),
                "size": entry.get("size"),
            }
        )
    return system_info, resolved, unresolved


def sha1_of_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_path_to_url(repo_path):
    # Codifica cada segmento de la ruta (hay espacios y paréntesis en
    # nombres de fabricante/sistema) sin tocar las barras separadoras.
    segments = repo_path.split("/")
    return RAW_BASE_URL + "/".join(urllib.parse.quote(seg) for seg in segments)


def download_file(url, dest_path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".part"
    with open(tmp_path, "wb") as fh:
        fh.write(data)
    os.replace(tmp_path, dest_path)


def human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def fetch_system(native_id, registry, dest_index, dry_run=False, force=False):
    """
    Descarga (o verifica) los ficheros de un sistema. Devuelve
    (ok_count, downloaded_count, failed_count, skipped_count).
    """
    system_info, resolved, unresolved = resolve_system_files(native_id, registry, dest_index)

    if system_info is None:
        log_err(f"Sistema desconocido para RetroBIOS/Batocera: '{native_id}'. "
                f"Usa --list para ver los disponibles.")
        return 0, 0, 0, 0, True

    log(f"\n=== {system_info['name']} ({native_id}) ===")

    for dest in unresolved:
        log_warn(f"  '{dest}' no se encontró en el manifiesto de instalación; se omite.")

    if not resolved:
        log("  (sin ficheros que descargar)")
        return 0, 0, 0, 0, False

    ok = downloaded = failed = skipped = 0

    for f in resolved:
        local_path = os.path.join(BIOS_DIR, f["destination"])
        size_txt = human_size(f["size"]) if f.get("size") else "?"

        if os.path.isfile(local_path) and not force:
            if f.get("sha1") and sha1_of_file(local_path) == f["sha1"]:
                log(f"  [OK]      {f['destination']} ({size_txt}) — ya presente")
                ok += 1
                continue
            else:
                log_warn(f"  {f['destination']} existe pero no coincide su hash; se redescarga.")

        if dry_run:
            log(f"  [DRY-RUN] {f['destination']} ({size_txt}) <- {f['repo_path']}")
            skipped += 1
            continue

        url = repo_path_to_url(f["repo_path"])
        try:
            download_file(url, local_path)
        except (urllib.error.URLError, TimeoutError) as exc:
            log_err(f"  [FAIL]    {f['destination']}: descarga fallida ({exc})")
            failed += 1
            continue

        if f.get("sha1"):
            actual = sha1_of_file(local_path)
            if actual != f["sha1"]:
                log_err(f"  [FAIL]    {f['destination']}: hash no coincide tras descargar "
                        f"(esperado {f['sha1']}, obtenido {actual}); se elimina.")
                os.remove(local_path)
                failed += 1
                continue

        log(f"  [OK]      {f['destination']} ({size_txt}) — descargado")
        downloaded += 1

    return ok, downloaded, failed, skipped, False


def list_systems(registry):
    log(f"{'native_id':22s} {'nombre':30s} ficheros")
    for native_id, info in sorted(registry.items()):
        log(f"{native_id:22s} {info['name']:30s} {len(info['files'])}")
    log(f"\n{len(registry)} sistemas disponibles.")


def main(argv):
    parser = argparse.ArgumentParser(
        prog="bios-fetch",
        description="Descarga BIOS de Batocera desde RetroBIOS (Abdess/retrobios), por sistema.",
    )
    parser.add_argument("systems", nargs="*", help="native_id de los sistemas a descargar (p.ej. psx gba dreamcast)")
    parser.add_argument("--all", action="store_true", help="descarga todos los sistemas conocidos (~1.2 GB)")
    parser.add_argument("--list", action="store_true", help="lista los sistemas disponibles y sale")
    parser.add_argument("--dry-run", action="store_true", help="muestra qué se descargaría, sin escribir nada")
    parser.add_argument("--force", action="store_true", help="redescarga aunque el fichero ya esté presente y correcto")
    parser.add_argument("--refresh", action="store_true", help="fuerza refresco del manifiesto de RetroBIOS aunque la caché sea reciente")
    args = parser.parse_args(argv)

    platform_path, install_path = ensure_manifests(force_refresh=args.refresh)
    platform_manifest = load_platform_manifest(platform_path)
    install_manifest = load_install_manifest(install_path)
    registry = build_system_registry(platform_manifest)
    dest_index = build_dest_index(install_manifest)

    if args.list:
        list_systems(registry)
        return 0

    if args.all:
        targets = sorted(registry.keys())
    else:
        targets = args.systems

    if not targets:
        parser.print_help()
        return 1

    total_ok = total_dl = total_fail = total_skip = 0
    any_unknown = False

    for native_id in targets:
        ok, dl, fail, skip, unknown = fetch_system(
            native_id, registry, dest_index, dry_run=args.dry_run, force=args.force
        )
        total_ok += ok
        total_dl += dl
        total_fail += fail
        total_skip += skip
        any_unknown = any_unknown or unknown

    log("\n" + "=" * 60)
    log(f"Resumen: {total_ok} ya presentes, {total_dl} descargados, "
        f"{total_fail} fallidos, {total_skip} simulados (dry-run).")

    if total_fail:
        return 1
    if any_unknown:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        # p.ej. cuando la salida se corta con `| head`; no es un fallo real.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)