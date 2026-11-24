"""Utilidades mínimas sobre dbus-fast (llamadas directas, sin introspección)."""

from __future__ import annotations

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

from .i18n import _

DBUS = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")


class DBusCallError(RuntimeError):
    def __init__(self, name: str, text: str) -> None:
        super().__init__(f"{name}: {text}")
        self.name = name


class NoSessionBus(OSError):
    """No hay bus de sesión (fuera de una sesión gráfica, en un contenedor…)."""


async def session_bus() -> MessageBus:
    try:
        return await MessageBus(bus_type=BusType.SESSION).connect()
    except Exception as e:
        raise NoSessionBus(
            _("cannot connect to the DBus session bus (run it inside your desktop session): {error}").format(error=e)
        ) from None


async def call(bus: MessageBus, dest: str, path: str, iface: str, member: str, sig: str = "", body=None):
    reply = await bus.call(
        Message(destination=dest, path=path, interface=iface, member=member, signature=sig, body=body or [])
    )
    if reply.message_type == MessageType.ERROR:
        raise DBusCallError(reply.error_name or "error", " ".join(map(str, reply.body)))
    return reply.body


async def get_prop(bus: MessageBus, dest: str, path: str, iface: str, prop: str):
    (v,) = await call(bus, dest, path, "org.freedesktop.DBus.Properties", "Get", "ss", [iface, prop])
    return v.value


async def name_available(bus: MessageBus, name: str) -> bool:
    """True si el nombre tiene dueño o es activable por DBus."""
    (has,) = await call(bus, *DBUS, "NameHasOwner", "s", [name])
    if has:
        return True
    (names,) = await call(bus, *DBUS, "ListActivatableNames")
    return name in names
