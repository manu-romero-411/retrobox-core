"""Start Retrobox from the settings window ("Accept and open Retrobox")."""

from __future__ import annotations

import subprocess

from retrobox.paths import BIN_DIR, fresh_environment


def launch_retrobox() -> None:
    """Start ``retrobox`` on its own, so it outlives the settings window.

    It gets the environment this window was started with, not the current one:
    the directories and [environ] values read from retrobox.ini before the user
    changed it are left out, so it resolves them again from the saved file.

    Raises:
        OSError: If it can't be started.
    """
    subprocess.Popen(  # pylint: disable=consider-using-with  # it must outlive us
        [str(BIN_DIR / "retrobox")],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=fresh_environment(),
        start_new_session=True,
    )
