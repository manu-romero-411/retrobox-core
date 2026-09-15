"""
Base runtime paths module.

Zero knowledge of configgen, launcher, frontend (EmulationStation),
or gamepadly. Only generic path resolution (XDG, ROOTDIR) and filesystem
helpers. This is the only module in the package that other subsystems
of the project (outside of retrobox_paths) should consider truly
"independent".
"""

from __future__ import annotations

import configparser
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Final, overload

if TYPE_CHECKING:
    from _typeshed import (
        OpenBinaryModeUpdating,
        OpenBinaryModeWriting,
        OpenTextModeUpdating,
        OpenTextModeWriting,
    )
    from collections.abc import Generator, Iterable
    from io import BufferedRandom, BufferedWriter, TextIOWrapper


def check_env_dirs(variable: str, default_dir: Path) -> Path:
    """
    Safely assign directory values with environment variable overrides.

    Checks if the environment variable `variable` is set and points to
    a valid, readable directory. If so, returns that path; otherwise,
    returns `default_dir`.

    Args:
        variable: The environment variable name to check.
        default_dir: The fallback directory path if the override is invalid.

    Returns:
        The resolved directory path.
    """
    override = Path(os.environ.get(variable, str(default_dir)))
    if override.exists() and override.is_dir() and os.access(override, os.R_OK):
        return override
    return default_dir


# ---------------------------------------------------------------------------
# retrobox.ini: bootstrap, auto-generation and self-healing
#
# Three sections with distinct contracts:
#   [core]    -> Core behavior flags: autocorrect_paths, ignore_systems.
#   [paths]   -> Keys managed by this module (roms_dir, saves_dir,
#                bios_dir). Always present. If autocorrect_paths is true,
#                they are guaranteed to be valid directories (auto-healed
#                if missing or invalid). Read directly via get_configured_path().
#   [environ] -> Literal dump to os.environ (API keys, STEAM_LIBRARY_DIR,
#                etc.). No validation or self-healing: whatever is written
#                there is respected as-is, case included (these become
#                actual environment variable names).
#
# [core] and [paths] key names are lowercase by convention (they're our
# own parameters, not env var names). Older retrobox.ini files that still
# have them UPPERCASE are transparently migrated to lowercase the first
# time they're loaded -- see _normalize_section_keys().
# ---------------------------------------------------------------------------

# Path keys that retrobox.ini must always have, with their default
# subdirectory relative to RETROBOX_ROOTDIR (never a fixed absolute path:
# resolved at runtime against "rootdir").
_PATH_DEFAULTS: Final[dict[str, str]] = {
    "roms_dir": "roms",
    "saves_dir": "saves",
    "bios_dir": "bios",
}

# [core] keys that aren't paths (no auto-healing/directory creation),
# with their default value if missing.
_CORE_DEFAULTS: Final[dict[str, str]] = {
    "autocorrect_paths": "true",
    "ignore_systems": "",
}


class CaseSensitiveConfigParser(configparser.ConfigParser):
    """
    A ConfigParser subclass that preserves the case of option keys.

    By default, ConfigParser lowercases all option names. This subclass
    overrides `optionxform` to return the option string unchanged. This
    is also the standard way to fix Pylance/Pyright type errors when
    trying to assign `str` to `optionxform` (since it's typed as a method
    in typeshed, not a simple attribute).
    """

    def optionxform(self, optionstr: str) -> str:
        """Return the option string unchanged to preserve case."""
        return optionstr


def _default_path_value(rootdir: Path, subdir: str) -> str:
    """
    Compute the default absolute path for a given subdirectory.

    Args:
        rootdir: The base root directory.
        subdir: The subdirectory name relative to rootdir.

    Returns:
        The resolved absolute path as a string.
    """
    return str((rootdir / subdir).resolve())


def _normalize_section_keys(
    config: CaseSensitiveConfigParser, section: str, canonical_keys: "Iterable[str]"
) -> bool:
    """
    Rename any keys in `section` that case-insensitively match one of
    `canonical_keys` to their canonical (lowercase) spelling.

    [core] and [paths] key names used to be UPPERCASE (e.g. ROMS_DIR,
    AUTOCORRECT_PATHS); they're now lowercase (roms_dir,
    autocorrect_paths). This keeps older retrobox.ini files working by
    renaming the key in place -- the value is preserved, only the key
    spelling changes. Unrelated to [environ], which is never touched
    (its keys are real environment variable names and keep whatever
    case the user wrote).

    Args:
        config: The loaded ConfigParser.
        section: Section name to normalize ("core" or "paths").
        canonical_keys: The lowercase key names to normalize towards.

    Returns:
        True if any key was renamed (i.e. the ini needs to be rewritten).
    """
    changed = False
    lookup = {k.lower(): k for k in canonical_keys}

    for existing_key in list(config[section].keys()):
        canonical = lookup.get(existing_key.lower())
        if canonical and existing_key != canonical:
            value = config.get(section, existing_key)
            config.remove_option(section, existing_key)
            config.set(section, canonical, value)
            changed = True

    return changed


def _ensure_retrobox_ini(rootdir: Path, ini_path: Path) -> CaseSensitiveConfigParser:
    """
    Load retrobox.ini (if it exists) and guarantee that the [paths] section
    behaves according to the [core] autocorrect_paths flag.

    - If the .ini does not exist yet (first boot), it is created with
      autocorrect_paths=true, ignore_systems empty, and the three path
      keys pointing to their defaults (absolute paths, resolved against
      rootdir).
    - Any [core]/[paths] key still spelled UPPERCASE from an older
      retrobox.ini (e.g. ROMS_DIR, AUTOCORRECT_PATHS) is renamed in
      place to its current lowercase spelling, preserving its value.
    - If autocorrect_paths is true and a path key is missing, empty, or
      points to a non-existent/unreadable directory, it is replaced with
      the default path and that default folder is created.
    - If autocorrect_paths is false, invalid or missing paths are left
      exactly as they are in the file, without creating directories or
      overwriting the user's configuration.
    - The [environ] section is left as-is: its contents (including key
      case) are not validated or repaired here, only dumped literally
      into os.environ by _bootstrap_env().

    The file is rewritten to disk only if something has changed.

    Args:
        rootdir: The base root directory for resolving default paths.
        ini_path: The path to the retrobox.ini file.

    Returns:
        The loaded and potentially repaired ConfigParser instance.
    """
    config = CaseSensitiveConfigParser()

    if ini_path.is_file():
        config.read(ini_path)

    changed = not ini_path.is_file()

    # Ensure all required sections exist
    for section in ("core", "paths", "environ"):
        if not config.has_section(section):
            config.add_section(section)
            changed = True

    # Migrate any leftover UPPERCASE keys from older retrobox.ini files to
    # their current lowercase spelling. [environ] is intentionally left
    # alone -- its keys are real environment variable names.
    if _normalize_section_keys(config, "core", _CORE_DEFAULTS.keys()):
        changed = True
    if _normalize_section_keys(config, "paths", _PATH_DEFAULTS.keys()):
        changed = True

    # Determine if autocorrection is enabled (default to True for backward compatibility)
    autocorrect_raw = config.get("core", "autocorrect_paths", fallback="true").strip().lower()
    autocorrect = autocorrect_raw in ("true", "1", "yes", "on")

    # Fill in any missing [core] keys (autocorrect_paths, ignore_systems)
    # with their defaults, without touching keys that are already set.
    for key, default_value in _CORE_DEFAULTS.items():
        if key not in config["core"]:
            config.set("core", key, default_value)
            changed = True

    for key, subdir in _PATH_DEFAULTS.items():
        current = config.get("paths", key, fallback="").strip()
        valid = bool(current) and Path(current).is_dir() and os.access(current, os.R_OK)

        if not valid:
            if autocorrect:
                default_value = _default_path_value(rootdir, subdir)
                # Ensure the default path actually exists on disk, so that
                # whoever reads it later (get_configured_path) finds it available.
                Path(default_value).mkdir(parents=True, exist_ok=True)
                config.set("paths", key, default_value)
                changed = True
            else:
                # Autocorrect is disabled: do not overwrite the invalid/missing path
                # and do not create the directory. Leave it as the user specified (or empty).
                pass

    if changed:
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        with ini_path.open("w", encoding="utf-8") as f:
            config.write(f)

    return config


def _bootstrap_env(rootdir: Path) -> CaseSensitiveConfigParser:
    """
    Bootstrap environment variables from retrobox.ini.

    Lives here (and not in startup/env_handling.py) because it must run
    BEFORE the Final constants of this package are computed, and we no
    longer want to depend on whoever imports us remembering to call it
    in the correct order on their own.

    Only [environ] is dumped into os.environ. [paths] is left in the
    returned ConfigParser, which get_configured_path() queries directly:
    managed paths never reach environ.

    Args:
        rootdir: The base root directory.

    Returns:
        The parsed ConfigParser instance.
    """
    config = _ensure_retrobox_ini(rootdir, rootdir / "retrobox.ini")
    for key, value in config.items("environ"):
        value = value.strip()
        # An empty value is interpreted as "undefined": it falls back to
        # the default of whoever consumes it instead of overwriting with "".
        if key and value:
            os.environ.setdefault(key, value)
    return config


def get_configured_path(key: str, default: Path) -> Path:
    """
    Read `key` from the [paths] section of retrobox.ini, already validated
    (or intentionally left as-is if autocorrect_paths=false) by 
    _ensure_retrobox_ini during bootstrap.

    Does not touch os.environ or disk: it's a simple read from the
    in-memory ConfigParser. If the key is missing or empty, it falls 
    back to `default`.

    Args:
        key: The path key to retrieve (e.g., "roms_dir").
        default: The fallback Path if the key is missing or empty.

    Returns:
        The configured Path.
    """
    value = _PATHS_CONFIG.get("paths", key, fallback="").strip()
    return Path(value) if value else default


def get_ignored_systems() -> frozenset[str]:
    """
    Read the [core] ignore_systems key from retrobox.ini.

    ignore_systems is a comma-separated list of system names (matching
    the top-level key used in each resources/systems_config/.../*.yaml
    file, e.g. "gba", "psp") that should be skipped when generating
    es_systems.cfg.

    Does not touch os.environ or disk: like get_configured_path(), it's
    a simple read from the in-memory ConfigParser already bootstrapped
    by _ensure_retrobox_ini.

    Returns:
        A frozenset of lowercased, whitespace-stripped system names.
        Empty if the key is missing or blank.
    """
    raw = _PATHS_CONFIG.get("core", "ignore_systems", fallback="")
    return frozenset(name.strip().lower() for name in raw.split(",") if name.strip())


# ---------------------------------------------------------------------------
# Bootstrap: retrobox.ini must be applied BEFORE computing any Final
# constants in this package (here and in _configgen.py / _frontend.py /
# _gamepadly.py, which import RETROBOX_ROOTDIR / RESOURCES_DIR / USERDATA
# from here). By living in the package's own import, it no longer depends
# on retrobox_run.py (or any future entrypoint) remembering to call it in
# the correct order before importing retrobox_paths.
# ---------------------------------------------------------------------------
_ROOTDIR_GUESS: Final[Path] = Path(__file__).resolve().parents[2]
_PATHS_CONFIG: Final[CaseSensitiveConfigParser] = _bootstrap_env(
    Path(os.environ.get("RETROBOX_ROOTDIR", str(_ROOTDIR_GUESS)))
)

# XDG Helpers
_USER_HOME: Final[Path] = Path.home()
_XDG_DATA: Final[Path] = Path.home() / ".local" / "share"
_XDG_CACHE: Final[Path] = Path.home() / ".cache"
_XDG_CONFIG: Final[Path] = Path.home() / ".config"
_SYSTEM_LOCAL_BIN: Final[Path] = Path("/usr/local/bin")
_SYSTEM_LOCAL_SHARE: Final[Path] = Path("/usr/local/share")

# ---------------------------------------------------------------------------
# System installation paths (same as in batocera)
# ---------------------------------------------------------------------------
RETROBOX_ROOTDIR: Final[Path] = check_env_dirs("RETROBOX_ROOTDIR", _ROOTDIR_GUESS)

USERDATA: Final[Path] = RETROBOX_ROOTDIR

ENV_FILE: Final[Path] = RETROBOX_ROOTDIR / ".env"
RETROBOX_INI: Final[Path] = RETROBOX_ROOTDIR / "retrobox.ini"

RESOURCES_DIR: Final[Path] = RETROBOX_ROOTDIR / "resources"
DATAINIT_DIR: Final[Path] = RESOURCES_DIR / "datainit"
DEFAULTS_DIR: Final[Path] = RESOURCES_DIR / "configgen"

HOME_INIT: Final[Path] = DATAINIT_DIR / "system"
CONF_INIT: Final[Path] = HOME_INIT / "configs"
EMULATORS: Final[Path] = USERDATA / "emulators"
ROMS: Final[Path] = get_configured_path("roms_dir", USERDATA / "roms")

IGNORED_SYSTEMS: Final[frozenset[str]] = get_ignored_systems()

CACHE: Final[Path] = _XDG_CACHE / "retrobox"
LOGS: Final[Path] = USERDATA / "logs"

HOOKS: Final[Path] = USERDATA / "resources" / "hooks" / "retrohook"


# ---------------------------------------------------------------------------
# Generic filesystem utilities
# ---------------------------------------------------------------------------
def mkdir_if_not_exists(directory: Path) -> None:
    """
    Create a directory and its parents if they do not exist.

    Handles edge cases where the path exists but is not a valid directory
    (e.g., broken symlink or regular file). If it's a broken symlink, it
    is removed. If it's a regular file, it is renamed with a timestamp
    backup to avoid data loss.

    Args:
        directory: The directory path to create.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        # If it's a broken symlink, remove it and create the directory
        if directory.is_symlink():
            directory.unlink()
            directory.mkdir(parents=True, exist_ok=True)
        else:
            # If it's a regular file, rename it to avoid data loss and create the directory
            backup_name = f"{directory.name}.bak_{int(time.time())}"
            directory.rename(directory.with_name(backup_name))
            directory.mkdir(parents=True, exist_ok=True)


def ensure_symlink(source: Path, link: Path) -> None:
    """
    Guarantee that a symlink exists: link -> source.

    Safety guarantees:
    - Does not delete non-empty directories.
    - Avoids symlink cycles.
    - Does not touch anything if it's already correct.

    Args:
        source: The target path the symlink should point to.
        link: The path where the symlink should be created.

    Raises:
        RuntimeError: If a symlink cycle is detected or if refusing to
                      replace a non-empty directory.
    """
    source = source.resolve()

    # --- 1. Avoid self-reference ---
    if link.resolve() == source:
        return

    # --- 2. Detect cycles (link inside source or vice versa) ---
    try:
        if source in link.resolve().parents:
            raise RuntimeError(f"Symlink loop detected: {link} -> {source}")
    except FileNotFoundError:
        # link does not exist yet → ok
        pass

    # --- 3. If it already exists ---
    if link.exists() or link.is_symlink():
        # --- Case A: already a symlink ---
        if link.is_symlink():
            try:
                if link.resolve() == source:
                    return  # already correct
            except FileNotFoundError:
                pass  # broken symlink → recreate it

            link.unlink()
            link.symlink_to(source)
            return

        # --- Case B: real directory ---
        if link.is_dir():
            # critical protection
            if any(link.iterdir()):
                raise RuntimeError(f"Refusing to replace non-empty directory: {link}")

            shutil.rmtree(link)
            link.symlink_to(source)
            return

        # --- Case C: regular file ---
        link.unlink()
        link.symlink_to(source)
        return

    # --- 4. Does not exist ---
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(source)


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenTextModeWriting | OpenTextModeUpdating
) -> Generator[TextIOWrapper, None, None]: ...


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenBinaryModeUpdating
) -> Generator[BufferedRandom, None, None]: ...


@overload
def ensure_parents_and_open(
    file: Path, mode: OpenBinaryModeWriting
) -> Generator[BufferedWriter, None, None]: ...


@contextmanager
def ensure_parents_and_open(file: Path, mode: str) -> Generator[IO[Any], None, None]:
    """
    Ensure parent directories exist and open a file.

    Creates the parent directories of `file` if they do not exist, then
    opens the file with the given mode. This is a context manager that
    yields the file object.

    Args:
        file: The file path to open.
        mode: The mode in which to open the file (e.g., 'w', 'rb').

    Yields:
        The opened file object.
    """
    mkdir_if_not_exists(file.parent)
    # Explicitly set UTF-8 for text modes to avoid Pylint unspecified-encoding warnings
    encoding = "utf-8" if "b" not in mode else None
    with file.open(mode, encoding=encoding) as f:
        yield f