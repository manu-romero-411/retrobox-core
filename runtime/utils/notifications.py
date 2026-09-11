"""
Desktop notification helpers.

Uses the `notify-send` CLI (Freedesktop.org standard) so it works across
KDE Plasma, GNOME, XFCE, and any other DE implementing the standard
org.freedesktop.Notifications D-Bus interface.

Falls back silently if `notify-send` is not installed or the call fails:
notifications are a best-effort UX improvement, never a hard requirement.
"""

from __future__ import annotations

import shutil
import subprocess


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
    Send a desktop notification via `notify-send`.

    Args:
        summary: Short title of the notification.
        body: Optional longer message body.
        urgency: One of "low", "normal", "critical".
        icon: Icon name from the current icon theme (e.g. "dialog-error").
        app_name: Application name shown in the notification.
        timeout_ms: How long the notification stays on screen (ms).

    Returns:
        True if the notification was dispatched successfully, False otherwise.
    """
    notify_send = shutil.which("notify-send")
    if notify_send is None:
        return False

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
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def notify_error(summary: str, body: str = "") -> bool:
    """
    Convenience wrapper for error-level notifications.

    Uses "critical" urgency and the "dialog-error" icon so the DE
    renders it prominently.
    """
    return send_desktop_notification(
        summary,
        body,
        urgency="critical",
        icon="dialog-error",
    )