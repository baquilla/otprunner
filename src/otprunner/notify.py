"""Notificaciones de escritorio (org.freedesktop.Notifications). Nunca lanza excepciones."""

from __future__ import annotations

import logging

from dbus_fast import Variant

from . import APP_NAME
from .dbusutil import call

log = logging.getLogger(__name__)

DEST = ("org.freedesktop.Notifications", "/org/freedesktop/Notifications", "org.freedesktop.Notifications")


async def notify(bus, summary: str, body: str = "", icon: str = "otprunner", *,
                 timeout_ms: int = 5000, transient: bool = False, error: bool = False) -> None:
    hints = {"desktop-entry": Variant("s", "otprunner")}
    if transient:
        hints["transient"] = Variant("b", True)
    if error:
        hints["urgency"] = Variant("y", 2)
        icon = "dialog-error"
    try:
        await call(bus, *DEST, "Notify", "susssasa{sv}i",
                   [APP_NAME, 0, icon, summary, body, [], hints, timeout_ms])
    except Exception as e:  # noqa: BLE001 — una notificación fallida no debe romper nada
        log.warning("no se pudo notificar (%s): %s — %s", e, summary, body)
