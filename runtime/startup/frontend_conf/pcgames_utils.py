import json
import logging
import re
import sqlite3
from pathlib import Path

from .pcgames_paths import (
    _EPIC_JSON,
    _GOG_JSON,
    _INVALID_FILENAME_CHARS,
    _LUTRIS_DB_CANDIDATES,
    _HEROIC_SIDELOAD_JSON,
    _SKIP_NAME_RE,
    _STEAM_ROOTS
)

# logging.basicConfig(
#     level=logging.INFO,
#     format="[%(levelname)s] %(message)s"
# )

_logger = logging.getLogger(__name__)

def _clear_name(name: str) -> str:
    return name.translate(_INVALID_FILENAME_CHARS).strip()

def _write_heroic_link(target: Path, nombre: str, app_name: str, runner: str) -> None:
    name_clean = _clear_name(nombre)
    link = f"heroic://launch?appName={app_name}&runner={runner}"
    file_path = target / f"{name_clean}.heroic"
    file_path.write_text(link + "\n", encoding="utf-8")
    _logger.debug("[%s] %s.heroic -> %s", runner, name_clean, link)
 
def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("Couldn't read %s: %s", path, exc)
        return None

def _vdf_get(texto: str, clave: str) -> str:
    match = re.search(rf'"{re.escape(clave)}"\s*"([^"]*)"', texto, re.IGNORECASE)
    return match.group(1) if match else ""

def _clear_pcgame_links(system_dir: Path, ext: str) -> None:
    _logger.info("Deleting %s links for clean import: %s", ext, system_dir)

    if not system_dir.is_dir():
        return
    for f in system_dir.glob(f"*.{ext}"):
        f.unlink(missing_ok=True)
    return

def lutris_es_sync(target: Path):
    """Escanea los juegos instalados en Lutris (vía su base SQLite) y genera
    un .lynx por cada uno en `destino`."""
    lutris_db = next((c for c in _LUTRIS_DB_CANDIDATES if c.is_file()), None)
    if lutris_db is None:
        _logger.debug("lutris database not found at: %s", _LUTRIS_DB_CANDIDATES)
        return 0

    _logger.debug("Database found: %s", lutris_db)

    target.mkdir(parents=True, exist_ok=True)
    _clear_pcgame_links(target, "lynx")

    con = sqlite3.connect(str(lutris_db))
    try:
        rows = con.execute(
            "SELECT id, name, runner FROM games WHERE installed=1 ORDER BY name;"
        ).fetchall()
    finally:
        con.close()

    total = 0
    for game_id, nombre, runner in rows:
        if not game_id or not nombre:
            continue
        name_clean = _clear_name(nombre)
        link = f"lutris:rungameid/{game_id}"
        file_path = target / f"{name_clean}.lynx"
        file_path.write_text(link + "\n", encoding="utf-8")
        _logger.debug("[%s] %s.lynx -> %s", runner or "sin runner", name_clean, link)
        total += 1

    _logger.info("%d lutris launchers generated at %s", total, target)

def steam_es_sync(target: Path) -> int:
    """Escanea los juegos instalados en Steam (todas las bibliotecas) y genera
    un .steam por cada uno en `destino`. Devuelve el número de ficheros generados."""
    steam_root = next((r for r in _STEAM_ROOTS if (r / "steamapps").is_dir()), None)
    if steam_root is None:
        _logger.debug("Steam installation not found at: %s", _STEAM_ROOTS)
        return 0

    _logger.debug("Steam found at: %s", steam_root)
    _clear_pcgame_links(target, "steam")

    library_vdf = next(
        (c for c in (steam_root / "steamapps" / "libraryfolders.vdf", steam_root / "libraryfolder.vdf") if c.is_file()),
        None,
    )
    if library_vdf is None:
        _logger.debug("Couldn't find steam library files (libraryfolders.vdf / libraryfolder.vdf)")
        return 0

    _logger.debug("steam library read from: %s", library_vdf)

    library_paths = [
        Path(p)
        for p in re.findall(
            r'"path"\s*"([^"]*)"',
            library_vdf.read_text(encoding="utf-8", errors="ignore"),
            re.IGNORECASE,
        )
    ]
    library_paths.insert(0, steam_root)

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in library_paths:
        if p in seen:
            continue
        seen.add(p)
        unique_paths.append(p)

    target.mkdir(parents=True, exist_ok=True)

    total = 0
    found_libs = 0

    for lib in unique_paths:
        steamapps_dir = lib / "steamapps"
        if not steamapps_dir.is_dir():
            continue

        _logger.debug("Biblioteca: %s", steamapps_dir)
        found_libs += 1
        games_in_lib = 0

        for acf in sorted(steamapps_dir.glob("appmanifest_*.acf")):
            text = acf.read_text(encoding="utf-8", errors="ignore")
            appid = _vdf_get(text, "appid")
            name = _vdf_get(text, "name")

            if not appid or not name:
                continue

            if _SKIP_NAME_RE.search(name):
                _logger.debug("Skipping: %s (appid: %s)", name, appid)
                continue

            clean_name = _clear_name(name)
            link = f"steam://rungameid/{appid}"
            #executable = _vdf_get(text, "LaunchExecutable")
            file_path = target / f"{clean_name}.steam"
            file_path.write_text(f"{link}", encoding="utf-8")
            _logger.debug("%s.steam -> %s", clean_name, link)

            games_in_lib += 1
            total += 1

        if games_in_lib == 0:
            _logger.info("No steam games found in: %s", steamapps_dir)

    _logger.info(
        "%d steam launchers generated at %s (%d scanned libraries)",
        total, target, found_libs,
    )
    return total

def heroic_es_sync(target: Path) -> int:
    """Escanea los juegos instalados en Heroic (Epic/legendary, GOG y sideload)
    y genera un .heroic por cada uno en `target`. Devuelve el número de
    ficheros generados."""
    target.mkdir(parents=True, exist_ok=True)
    _clear_pcgame_links(target, "heroic")
 
    total = 0
 
    # Epic Games (legendary)
    data = _load_json(_EPIC_JSON)
    if data is not None:
        for entry in data.values():
            app_name = entry.get("app_name")
            titulo = entry.get("title")
            if not app_name or not titulo:
                continue
            _write_heroic_link(target, titulo, app_name, "legendary")
            total += 1
    else:
        _logger.info("Not found: %s", _EPIC_JSON)
 
    # GOG
    data = _load_json(_GOG_JSON)
    if data is not None:
        for entry in data.get("installed", []):
            app_name = entry.get("appName")
            install_path = entry.get("install_path", "")
            titulo = install_path.rstrip("/").split("/")[-1] if install_path else ""
            if not app_name or not titulo:
                continue
            _write_heroic_link(target, titulo, app_name, "gog")
            total += 1
    else:
        _logger.info("Not found: %s", _GOG_JSON)
 
    # Sideload / apps externas
    data = _load_json(_HEROIC_SIDELOAD_JSON)
    if data is not None:
        for entry in data:
            app_name = entry.get("app_name")
            titulo = entry.get("title")
            if not app_name or not titulo:
                continue
            _write_heroic_link(target, titulo, app_name, "sideload")
            total += 1
    else:
        _logger.info("Not found: %s", _HEROIC_SIDELOAD_JSON)
 
    _logger.info("%d Heroic launchers generated at %s", total, target)
    return total
 
