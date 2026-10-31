"""
Content Retrobox downloads before EmulationStation starts.

* ``theme``: the default theme, es-theme-iconic, into THEMES_DIR. Installed
  whenever EmulationStation has no theme at all (retrobox-core ships none).
* ``bezels``: the RetroBat bezels, the default decorations, into
  _DECORATIONS_DEF_DIR. Installed on the first start only (when that
  directory is still empty).

``retrobox --update-default-theme`` / ``--update-default-bezels`` download
them again, updating them or reinstalling them if they were removed.

Each package is the latest commit of a GitHub repository, streamed as a
tar.gz archive and unpacked on the fly (no archive is kept on disk, which
matters for the bezels). Everything is unpacked into a hidden staging
directory next to the target, and an installed copy is only replaced once
the new one is complete and valid: a failed or cancelled download leaves it
untouched. Nothing here stops the frontend from starting.

Run as ``python3 -m retrobox.startup.downloads PACKAGE...`` it downloads the
given packages, printing its progress: this is what the setup screen
(``retrobox.emusetup --download``) runs and shows.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, BinaryIO, Final

from retrobox.configgen.utils.logger import OK, setup_logging
from retrobox.paths import _DECORATIONS_DEF_DIR, FRONTEND_DIR, STATE_DIR, THEMES_DIR

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_logger = logging.getLogger(__name__)

_TIMEOUT_S: Final = 60
_CHUNK: Final = 1 << 16
_PROGRESS_EVERY_S: Final = 0.5
_MIB: Final = 1 << 20
# Present once Retrobox has started at least once (see is_first_start).
_FIRST_START_DONE: Final = STATE_DIR / "first-start.done"


@dataclass(frozen=True, slots=True)
class Package:
    """Something Retrobox downloads from GitHub."""

    name: str  # shown to the user
    url: str  # .tar.gz of a branch
    target: Path  # directory it is installed as
    marker: str = ""  # file that must be at the root of a valid copy


PACKAGES: Final[dict[str, Package]] = {
    "theme": Package(
        name="es-theme-iconic",
        url="https://github.com/manu-creative-411/es-theme-iconic/archive/refs/heads/main.tar.gz",
        target=THEMES_DIR / "es-theme-iconic",
        marker="theme.xml",
    ),
    "bezels": Package(
        name="RetroBat bezels",
        url="https://github.com/RetroBat-Official/retrobat-bezels/archive/refs/heads/master.tar.gz",
        target=_DECORATIONS_DEF_DIR,
    ),
}

_THEME_DIRS: Final = (FRONTEND_DIR / "themes", THEMES_DIR)


# ------------------------------------------------------------------ when
def has_theme() -> bool:
    """Whether EmulationStation has any theme (system-wide or the user's)."""
    for directory in _THEME_DIRS:
        try:
            if any(
                not entry.name.startswith(".") and (entry / "theme.xml").is_file()
                for entry in directory.iterdir()
            ):
                return True
        except OSError:
            continue
    return False


def _is_empty(directory: Path) -> bool:
    try:
        return not any(directory.iterdir())
    except OSError:
        return True


def is_first_start() -> bool:
    """True until mark_started() has been called once."""
    return not _FIRST_START_DONE.exists()


def mark_started() -> None:
    """Remember that Retrobox has started (see is_first_start)."""
    try:
        _FIRST_START_DONE.parent.mkdir(parents=True, exist_ok=True)
        _FIRST_START_DONE.touch()
    except OSError as exc:
        _logger.warning("Couldn't write %s: %s", _FIRST_START_DONE, exc)


def pending(update_theme: bool = False, update_bezels: bool = False) -> list[str]:
    """The packages to download before this start (keys of PACKAGES)."""
    keys = []
    if update_theme or not has_theme():
        keys.append("theme")
    if update_bezels or (is_first_start() and _is_empty(PACKAGES["bezels"].target)):
        keys.append("bezels")
    return keys


# -------------------------------------------------------------- download
class _Progress:  # pylint: disable=too-few-public-methods
    """A file-like wrapper over the HTTP response that prints how far it got."""

    def __init__(self, response: BinaryIO, total: int, name: str) -> None:
        self._response = response
        self._total = total
        self._name = name
        self._done = 0
        self._shown = 0.0

    def read(self, size: int = -1) -> bytes:
        """Read from the response, printing the progress now and then."""
        data = self._response.read(size if size > 0 else _CHUNK)
        self._done += len(data)
        now = time.monotonic()
        if now - self._shown >= _PROGRESS_EVERY_S:
            self._shown = now
            self._print()
        return data

    def finish(self) -> None:
        """Print the final figure and end the progress line."""
        self._print(end="\n")

    def _print(self, end: str = "") -> None:
        line = f"{self._name}: {self._done / _MIB:.1f}"
        if self._total > 0:
            percent = min(100, self._done * 100 // self._total)
            line += f" / {self._total / _MIB:.1f} MiB ({percent}%)"
        else:
            line += " MiB"
        # \r: the setup screen (like a terminal) rewrites the same line
        print(f"\r{line}", end=end, flush=True)


def _safe_members(archive: tarfile.TarFile) -> Iterable[tarfile.TarInfo]:
    """Regular files and directories that stay inside the destination."""
    for member in archive:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise tarfile.TarError(f"unsafe path in the archive: {member.name}")
        if member.isfile() or member.isdir():
            yield member


def _unpack(stream: _Progress, destination: Path) -> None:
    """Unpack a tar.gz stream into ``destination``, as it arrives."""
    # pylint: disable-next=consider-using-with
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:  # type: ignore[call-overload]
        extra = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
        for member in _safe_members(archive):
            archive.extract(member, destination, **extra)


def _root_of(extracted: Path, package: Package) -> Path:
    """The package's tree inside the archive (GitHub wraps it in one directory)."""
    entries = list(extracted.iterdir())
    root = entries[0] if len(entries) == 1 and entries[0].is_dir() else extracted
    if package.marker and not (root / package.marker).is_file():
        raise ValueError(f"no {package.marker} at the root of the archive")
    if _is_empty(root):
        raise ValueError("the archive is empty")
    return root


def install(package: Package) -> bool:
    """Download ``package`` and install it, replacing any previous copy.

    Returns:
        True if it was installed.
    """
    target = package.target
    if target.is_symlink():
        _logger.error("%s is a symlink; not replacing it", target)
        return False

    _logger.info("Downloading %s", package.name)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=target.parent) as tmp:
            staging = Path(tmp)
            extracted = staging / "extracted"
            extracted.mkdir()
            with urllib.request.urlopen(package.url, timeout=_TIMEOUT_S) as response:
                total = int(response.headers.get("Content-Length") or 0)
                progress = _Progress(response, total, package.name)
                try:
                    _unpack(progress, extracted)
                finally:
                    progress.finish()
            root = _root_of(extracted, package)

            # the previous copy goes into the staging directory, deleted on the way out
            if target.exists():
                target.rename(staging / "previous")
            root.rename(target)
    except (OSError, tarfile.TarError, ValueError) as exc:
        _logger.error("Couldn't install %s: %s", package.name, exc)
        return False

    _logger.log(OK, "%s installed in %s", package.name, target)
    return True


def install_all(keys: Sequence[str]) -> bool:
    """Install the packages ``keys``; True if all of them were installed."""
    results = [install(PACKAGES[key]) for key in keys]
    return all(results)


def labels(keys: Sequence[str]) -> str:
    """The packages ``keys`` as shown to the user."""
    return ", ".join(PACKAGES[key].name for key in keys)


# ------------------------------------------------------------------ CLI
def _handle_sigterm(signum: int, _frame: object) -> None:
    """Exit through the context managers, so that staging dirs are removed."""
    raise SystemExit(128 + signum)


def main(argv: Sequence[str] | None = None) -> int:
    """Download the packages named on the command line; 0 if all went fine."""
    parser = argparse.ArgumentParser(
        prog="python3 -m retrobox.startup.downloads",
        description="Download Retrobox's default content.",
    )
    parser.add_argument("packages", nargs="+", choices=sorted(PACKAGES))
    args = parser.parse_args(argv)
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGHUP, _handle_sigterm)
    with setup_logging():
        return 0 if install_all(args.packages) else 1


if __name__ == "__main__":
    sys.exit(main())
