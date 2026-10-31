"""Start Retrobox from the settings window ("Accept and open Retrobox")."""

from __future__ import annotations

import subprocess

from retrobox.paths import BIN_DIR


def launch_retrobox() -> None:
    """Start ``retrobox`` on its own, so it outlives the settings window.

    Raises:
        OSError: If it can't be started.
    """
    subprocess.Popen(  # pylint: disable=consider-using-with  # it must outlive us
        [str(BIN_DIR / "retrobox")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
