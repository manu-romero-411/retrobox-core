#!/usr/bin/env python3
"""
sgdb-artwork.py — Descarga marquee y thumb de SteamGridDB para juegos de EmulationStation
                  y actualiza el gamelist.xml con las rutas correctas.

Gestiona las colecciones steam/, heroic/ y lutris/ leyendo sus gamelist.xml.
Solo descarga -marquee.png y -thumb.png; los -image.png los gestiona ScreenScraper.

Convención de nombres en disco (igual que limpiar_nombre() en los sync scripts):
    Caracteres  / \\ : * ? " < > |  se sustituyen por  -
    El <name> del XML puede diferir; las rutas de archivo usan siempre clean_name().

Uso:
    python sgdb-artwork.py --roms /var/penguin/juegos/retrobox/roms --apikey TU_KEY
    python sgdb-artwork.py --roms /ruta/roms --apikey KEY --systems steam heroic
    python sgdb-artwork.py --roms /ruta/roms --apikey KEY --force
    python sgdb-artwork.py --roms /ruta/roms --apikey KEY --interactive

Selección automática (sin --interactive):
    Toma los 3 assets mejor valorados por la API y elige el de mayor score neto
    (upvotes - downvotes).

Selección manual (--interactive):
    Muestra hasta 10 candidatos por asset con score, dimensiones y autor para elegir.

Dependencias:
    pip install python-steamgriddb requests
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from steamgrid import SteamGridDB


# ── Constantes ───────────────────────────────────────────────────────────────

TOP_N_AUTO        = 3
TOP_N_INTERACTIVE = 10

LAUNCHER_NAMES = {"battle.net", "ubisoft connect", "epic games"}

# Tipos de asset que gestionamos
#   xml_tag   : etiqueta en gamelist.xml
#   suffix    : sufijo del archivo en disco  (sobre clean_name())
#   fetch     : método de la API  get_<fetch>_by_gameid
ASSET_DEFS = {
    "thumb": {
        "xml_tag": "thumbnail",
        "suffix":  "-thumb.png",
        "label":   "Thumb / Cover (grid vertical 2:3)",
        "fetch":   "grids",
    },
    "marquee": {
        "xml_tag": "marquee",
        "suffix":  "-marquee.png",
        "label":   "Marquee / Logo",
        "fetch":   "logos",
    },
}


# ── Normalización de nombre (≡ limpiar_nombre() en bash) ─────────────────────

_CLEAN_RE = re.compile(r'[/\\:*?"<>|]')

def clean_name(name: str) -> str:
    """
    Equivalente a limpiar_nombre() en los sync scripts de bash:
      - Sustituye  / \\ : * ? " < > |  por  -
      - Hace strip de espacios en los extremos
    """
    return _CLEAN_RE.sub("-", name).strip()


# ── Helpers de descarga ──────────────────────────────────────────────────────

def download_url(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      ✗ Error descargando {url}: {e}")
        return False


def net_score(asset) -> int:
    up   = getattr(asset, "upvotes",   0) or 0
    down = getattr(asset, "downvotes", 0) or 0
    return up - down


def fmt_asset(i: int, asset) -> str:
    dims   = f"{asset.width}×{asset.height}" if asset.width else "?×?"
    author = asset.author.name if asset.author else "?"
    score  = net_score(asset)
    mime   = getattr(asset, "mime", "?") or "?"
    return f"   [{i:2d}] score={score:+d}  {dims:>10}  {mime:<11}  autor: {author}"


# ── Obtención de assets ──────────────────────────────────────────────────────

# Dimensiones preferidas para grids (cover vertical ES)
GRID_PREFERRED_DIMS = "600x900"

def _is_static_png(asset) -> bool:
    """Descarta WebP y GIF; acepta PNG o mime vacío (la URL manda)."""
    mime = (getattr(asset, "mime", "") or "").lower()
    url  = (getattr(asset, "url",  "") or "").lower()
    if mime and "png" not in mime:
        return False
    if url.endswith((".webp", ".gif")):
        return False
    return True


def _is_2_3_ratio(asset) -> bool:
    """True si el asset tiene ratio aproximado 2:3 (covers verticales)."""
    w = getattr(asset, "width",  0) or 0
    h = getattr(asset, "height", 0) or 0
    if not w or not h:
        return False
    return abs((w / h) - (2 / 3)) < 0.05


def _fetch_raw_grids(sgdb_client: SteamGridDB, game_id: int, extra_queries: dict) -> list:
    """
    Llama directamente a _http.get_grid() para poder inyectar parámetros extra
    (como dimensions=600x900) que la API pública del wrapper no expone.
    Devuelve lista de objetos Grid o [] en caso de error/vacío.
    """
    from steamgrid import Grid
    try:
        payloads = sgdb_client._http.get_grid(
            [game_id], "game",
            queries={
                "nsfw":  "false",
                "humor": "false",
                **extra_queries,
            },
        )
        if payloads:
            return [Grid(p, sgdb_client._http) for p in payloads]
    except Exception:
        pass
    return []


def get_assets(sgdb_client: SteamGridDB, game_id: int, fetch_type: str, limit: int) -> list:
    """
    Devuelve hasta `limit` assets PNG estáticos para game_id.

    Para grids:
      1. Pide solo 600×900 (GRID_PREFERRED_DIMS) a la API.
      2. Si no hay resultados, fallback a cualquier dimensión filtrando ratio 2:3.
      3. Si tampoco hay ratio 2:3, devuelve cualquier PNG estático.

    Para logos/heroes: descarga todo y filtra PNG estáticos manualmente
    (el wrapper tiene bug de trailing space en ImageType.Static).
    """
    try:
        if fetch_type == "grids":
            # Intento 1: 600×900 exacto
            items = _fetch_raw_grids(sgdb_client, game_id,
                                     {"dimensions": GRID_PREFERRED_DIMS})
            items = [a for a in items if _is_static_png(a)]

            if not items:
                # Intento 2: cualquier dimensión, ratio 2:3
                all_items = _fetch_raw_grids(sgdb_client, game_id, {})
                png_items = [a for a in all_items if _is_static_png(a)]
                items = [a for a in png_items if _is_2_3_ratio(a)]
                if not items:
                    # Fallback final: cualquier PNG
                    items = png_items
                    if items:
                        print(f"      ⚠ Sin grids 600×900 ni ratio 2:3 — usando cualquier PNG")
                else:
                    print(f"      ⚠ Sin grids 600×900 — usando ratio 2:3")

        elif fetch_type == "logos":
            raw = sgdb_client.get_logos_by_gameid([game_id])
            items = [a for a in (raw or []) if _is_static_png(a)]

        elif fetch_type == "heroes":
            raw = sgdb_client.get_heroes_by_gameid([game_id])
            items = [a for a in (raw or []) if _is_static_png(a)]

        else:
            return []

        return items[:limit]

    except Exception as e:
        print(f"      ✗ Error obteniendo {fetch_type} (game_id={game_id}): {e}")
        return []


def pick_auto(assets: list):
    if not assets:
        return None
    return max(assets[:TOP_N_AUTO], key=net_score)


def pick_interactive(assets: list, label: str):
    if not assets:
        return None
    print(f"\n      Candidatos para {label}:")
    for i, a in enumerate(assets, 1):
        print(fmt_asset(i, a))
    print(f"   [ 0] Saltar este asset")
    while True:
        raw = input(f"      Elige [0-{len(assets)}]: ").strip()
        if raw == "0":
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(assets):
                return assets[idx]
        print("      Opción no válida.")


# ── Resolución de juego ──────────────────────────────────────────────────────

def resolve_game_id(sgdb_client: SteamGridDB, name: str) -> int | None:
    try:
        results = sgdb_client.search_game(name)
    except Exception as e:
        print(f"      ✗ Error buscando '{name}': {e}")
        return None

    if not results:
        print(f"      ✗ Sin resultados en SGDB para '{name}'")
        return None

    if len(results) == 1:
        return results[0].id

    # Coincidencia exacta de nombre
    exact = [r for r in results if r.name.lower() == name.lower()]
    if len(exact) == 1:
        return exact[0].id

    # Ambigüedad: preguntar
    print(f"\n      Múltiples resultados para '{name}':")
    shown = results[:8]
    for i, r in enumerate(shown, 1):
        year = r.release_date.year if getattr(r, "release_date", None) else "?"
        print(f"      [{i}] {r.name} ({year})  [id={r.id}]")
    print(f"      [0] Saltar este juego")

    while True:
        raw = input(f"      Elige [0-{len(shown)}]: ").strip()
        if raw == "0":
            return None
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(shown):
                return shown[idx].id
        print("      Opción no válida.")


# ── Actualización del gamelist.xml ───────────────────────────────────────────

def update_gamelist(gamelist_path: Path, name: str, file_stem: str, downloaded: dict[str, bool]) -> None:
    """
    Actualiza o inserta <thumbnail> y <marquee> en el <game> cuyo <name> coincide.
    Las rutas usan file_stem (stem del fichero launcher) para coincidir con los
    archivos en disco. Solo toca los tags de los assets descargados correctamente.
    """
    if not downloaded:
        return

    ET.register_namespace("", "")
    tree = ET.parse(gamelist_path)
    root = tree.getroot()

    # Buscar el <game> por <name>
    target = None
    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is not None and (name_el.text or "").strip() == name:
            target = game_el
            break

    if target is None:
        print(f"      ⚠ No se encontró '<name>{name}</name>' en el XML, no se actualiza.")
        return

    for key, success in downloaded.items():
        if not success:
            continue
        adef    = ASSET_DEFS[key]
        xml_tag = adef["xml_tag"]
        rel_path = f"./images/{file_stem}{adef['suffix']}"

        el = target.find(xml_tag)
        if el is None:
            # Insertar después de <image> si existe, si no al final
            el = ET.SubElement(target, xml_tag)
        el.text = rel_path

    # Escribir con indentación preservada (Python 3.9+)
    ET.indent(tree, space="\t")
    tree.write(gamelist_path, encoding="unicode", xml_declaration=True)
    print(f"      ✓ gamelist.xml actualizado")


# ── Procesado de un juego ────────────────────────────────────────────────────

def process_game(
    sgdb_client: SteamGridDB,
    name: str,
    file_stem: str,
    images_dir: Path,
    gamelist_path: Path,
    force: bool,
    interactive: bool,
) -> None:
    # Determinar qué assets necesitan descarga
    to_download: dict[str, Path] = {}
    for key, adef in ASSET_DEFS.items():
        dest = images_dir / (file_stem + adef["suffix"])
        if dest.exists() and not force:
            answer = input(f"   Ya existe '{dest.name}'. ¿Sobreescribir? [s/N]: ").strip().lower()
            if answer != "s":
                continue
        to_download[key] = dest

    if not to_download:
        print(f"   ✓ Sin cambios para '{name}'")
        return

    print(f"   Buscando '{name}' en SteamGridDB…")
    game_id = resolve_game_id(sgdb_client, name)
    if not game_id:
        print(f"   ✗ No se pudo resolver '{name}', saltando.")
        return

    print(f"   → game_id={game_id}")

    downloaded: dict[str, bool] = {}

    for key, dest in to_download.items():
        adef   = ASSET_DEFS[key]
        limit  = TOP_N_INTERACTIVE if interactive else TOP_N_AUTO
        assets = get_assets(sgdb_client, game_id, adef["fetch"], limit)

        if not assets:
            print(f"   ✗ Sin assets '{key}' disponibles en SGDB para '{name}'")
            downloaded[key] = False
            continue

        if interactive:
            chosen = pick_interactive(assets, adef["label"])
        else:
            chosen = pick_auto(assets)
            if chosen:
                print(f"   → {adef['label']}: score={net_score(chosen):+d}  "
                      f"{chosen.width}×{chosen.height}  {chosen.author.name}")

        if chosen is None:
            print(f"   — '{key}' saltado.")
            downloaded[key] = False
            continue

        ok = download_url(chosen.url, dest)
        downloaded[key] = ok
        if ok:
            print(f"   ✓ {dest.name}")

    # Actualizar gamelist.xml con los assets descargados correctamente
    update_gamelist(gamelist_path, name, file_stem, {k: v for k, v in downloaded.items() if v})


# ── Lectura del gamelist.xml ─────────────────────────────────────────────────

def parse_gamelist(gamelist_path: Path) -> list[dict]:
    tree = ET.parse(gamelist_path)
    root = tree.getroot()
    games = []

    for game_el in root.findall("game"):
        name_el = game_el.find("name")
        if name_el is None or not (name_el.text or "").strip():
            continue
        name = name_el.text.strip()
        if name.lower() in LAUNCHER_NAMES:
            continue

        # El stem del fichero launcher (.lynx/.steam/.heroic) es la fuente
        # canónica del nombre en disco — coincide con el prefijo de las imágenes.
        path_el = game_el.find("path")
        if path_el is not None and (path_el.text or "").strip():
            file_stem = Path(path_el.text.strip()).stem  # quita ./ y extensión
        else:
            file_stem = clean_name(name)  # fallback si falta <path>

        games.append({"name": name, "file_stem": file_stem})

    return games


# ── Punto de entrada ─────────────────────────────────────────────────────────

SUPPORTED_SYSTEMS = ["steam", "heroic", "lutris"]


def main():
    parser = argparse.ArgumentParser(
        description="Descarga marquee y thumb de SteamGridDB y actualiza gamelist.xml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--roms",    required=True, help="Ruta a la carpeta roms/")
    parser.add_argument("--apikey",  required=True, help="API key de SteamGridDB")
    parser.add_argument(
        "--systems", nargs="+", choices=SUPPORTED_SYSTEMS, default=SUPPORTED_SYSTEMS,
        help="Sistemas a procesar (por defecto: todos)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Sobreescribir archivos existentes sin preguntar",
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help=f"Mostrar {TOP_N_INTERACTIVE} candidatos por asset y dejar elegir",
    )
    args = parser.parse_args()

    roms_path = Path(args.roms)
    if not roms_path.is_dir():
        print(f"✗ La ruta '{roms_path}' no existe o no es un directorio.")
        sys.exit(1)

    sgdb_client = SteamGridDB(args.apikey)

    for system in args.systems:
        system_path  = roms_path / system
        gamelist     = system_path / "gamelist.xml"

        if not gamelist.exists():
            print(f"\n[{system}] ✗ No se encontró gamelist.xml, saltando.")
            continue

        games      = parse_gamelist(gamelist)
        images_dir = system_path / "images"

        print(f"\n{'═'*60}")
        print(f"  Sistema: {system}  ({len(games)} juegos)")
        print(f"{'═'*60}")

        for game in games:
            print(f"\n▸ {game['name']}")
            process_game(
                sgdb_client=sgdb_client,
                name=game["name"],
                file_stem=game["file_stem"],
                images_dir=images_dir,
                gamelist_path=gamelist,
                force=args.force,
                interactive=args.interactive,
            )

    print("\n✓ Proceso completado.")


if __name__ == "__main__":
    main()