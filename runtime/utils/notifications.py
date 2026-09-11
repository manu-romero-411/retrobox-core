"""
Desktop notification helpers.

Uses `notify-send` (Freedesktop.org standard) with a fallback to `kdialog` 
for KDE Plasma. Handles D-Bus environment variables to ensure it works 
even if the script is launched from a non-standard shell context.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

_logger = logging.getLogger(__name__)


def _get_dbus_address() -> str | None:
    """
    Ensure we have a valid D-Bus session address.
    Falls back to the default user socket path if the env var is missing.
    """
    if "DBUS_SESSION_BUS_ADDRESS" in os.environ:
        return os.environ["DBUS_SESSION_BUS_ADDRESS"]
    
    # Fallback for standard systemd user sessions
    uid = os.getuid()
    default_bus_path = f"/run/user/{uid}/bus"
    if os.path.exists(default_bus_path):
        return f"unix:path={default_bus_path}"
    
    return None


def send_desktop_notification(
    summary: str,
    body: str = "",
    *,
    urgency: str = "normal",
    icon: str = "dialog-information",
    app_name: str = "Retrobox",
    timeout_ms: int = 10000,
) -> bool:
    """
    Send a desktop notification via `notify-send` or `kdialog`.
    """
    env = os.environ.copy()
    dbus_addr = _get_dbus_address()
    if dbus_addr:
        env["DBUS_SESSION_BUS_ADDRESS"] = dbus_addr

    # 1. Try notify-send first (Universal)
    notify_send = shutil.which("notify-send")
    if notify_send:
        cmd = [
            notify_send,
            "--app-name", app_name,
            "--urgency", urgency,
            "--icon", icon,
            "--expire-time", str(timeout_ms),
            summary,
        ]
        if body:
            cmd.append(body)

        try:
            # CAPTURE OUTPUT TEMPORARILY TO DEBUG IF IT FAILS
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return True
            else:
                _logger.warning("notify-send failed: %s", result.stderr.strip())
        except (subprocess.SubprocessError, OSError) as e:
            _logger.warning("notify-send execution error: %s", e)

    # 2. Fallback to kdialog (Native KDE Plasma)
    if urgency == "critical" or urgency == "normal":
        kdialog = shutil.which("kdialog")
        if kdialog:
            kd_cmd = [kdialog, "--title", app_name]
            if urgency == "critical":
                kd_cmd.extend(["--error", f"{summary}\n\n{body}"])
            else:
                kd_cmd.extend(["--passivepopup", f"{summary}\n{body}", str(timeout_ms // 1000)])
            
            try:
                result = subprocess.run(
                    kd_cmd,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    return True
                else:
                    _logger.warning("kdialog failed: %s", result.stderr.strip())
            except (subprocess.SubprocessError, OSError) as e:
                _logger.warning("kdialog execution error: %s", e)

    return False


def notify_error(summary: str, body: str = "") -> bool:
    """Convenience wrapper for error-level notifications."""
    return send_desktop_notification(
        summary,
        body,
        urgency="critical",
        icon="dialog-error",
    )