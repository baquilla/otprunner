"""Backend Secret Service (org.freedesktop.secrets): GNOME Keyring, KeePassXC, KWallet ≥ KF 5.97.

Cada cuenta es un item de la colección por defecto con atributos
``application=<app>`` y ``account=<nombre>``; el secreto es la URI otpauth.
La sesión usa el algoritmo ``plain`` (el secreto viaja por el bus de sesión del usuario).
"""

from __future__ import annotations

import asyncio
import contextlib

from dbus_fast import Message, MessageType, Variant

from .. import APP_NAME
from ..dbusutil import DBusCallError, call, get_prop, name_available, session_bus
from ..i18n import _
from .base import Store, StoreError, StoreUnavailable

BUS = "org.freedesktop.secrets"
SERVICE_PATH = "/org/freedesktop/secrets"
I_SERVICE = "org.freedesktop.Secret.Service"
I_COLLECTION = "org.freedesktop.Secret.Collection"
I_ITEM = "org.freedesktop.Secret.Item"
I_PROMPT = "org.freedesktop.Secret.Prompt"
SCHEMA = "otprunner.Account"


class SecretServiceStore(Store):
    backend = "secretservice"

    def __init__(self, bus, app: str, owns_bus: bool) -> None:
        self.bus = bus
        self.app = app
        self._owns_bus = owns_bus
        self.session = "/"
        self.collection = "/"

    @classmethod
    async def open(cls, app: str = "otprunner", bus=None) -> SecretServiceStore:
        owns = bus is None
        bus = bus or await session_bus()
        try:
            if not await name_available(bus, BUS):
                raise StoreUnavailable(_("{service} is not on the session bus").format(service=BUS))
            self = cls(bus, app, owns)
            _out, self.session = await call(
                bus, BUS, SERVICE_PATH, I_SERVICE, "OpenSession", "sv", ["plain", Variant("s", "")]
            )
            (self.collection,) = await call(bus, BUS, SERVICE_PATH, I_SERVICE, "ReadAlias", "s", ["default"])
            if self.collection == "/":
                raise StoreUnavailable(_("the Secret Service has no default collection"))
            return self
        except DBusCallError as e:
            if owns:
                bus.disconnect()
            raise StoreUnavailable(str(e)) from None
        except BaseException:
            if owns:
                bus.disconnect()
            raise

    async def close(self) -> None:
        if self.session != "/":
            with contextlib.suppress(DBusCallError):
                await call(self.bus, BUS, self.session, "org.freedesktop.Secret.Session", "Close")
        if self._owns_bus:
            self.bus.disconnect()

    async def describe(self) -> str:
        try:
            (pid,) = await call(
                self.bus,
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "GetConnectionUnixProcessID",
                "s",
                [BUS],
            )
            try:
                with open(f"/proc/{pid}/comm") as f:
                    provider = f.read().strip()
            except OSError:
                provider = f"pid {pid}"
            label = await get_prop(self.bus, BUS, self.collection, I_COLLECTION, "Label")
            return _("Secret Service ({provider}), collection “{label}”").format(provider=provider, label=label)
        except DBusCallError:
            return "Secret Service"

    # --- desbloqueo y prompts ---------------------------------------------
    async def _prompt(self, prompt: str):
        if prompt == "/":
            return None
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        def handler(msg: Message):
            if (
                msg.message_type == MessageType.SIGNAL
                and msg.path == prompt
                and msg.interface == I_PROMPT
                and msg.member == "Completed"
                and not fut.done()
            ):
                fut.set_result(msg.body)

        rule = f"type='signal',interface='{I_PROMPT}',member='Completed',path='{prompt}'"
        await call(
            self.bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule]
        )
        self.bus.add_message_handler(handler)
        try:
            await call(self.bus, BUS, prompt, I_PROMPT, "Prompt", "s", [""])
            dismissed, result = await fut
        finally:
            self.bus.remove_message_handler(handler)
        if dismissed:
            raise StoreError(_("operation cancelled by the user"))
        return result.value

    async def _unlock(self) -> None:
        if not await get_prop(self.bus, BUS, self.collection, I_COLLECTION, "Locked"):
            return
        unlocked, prompt = await call(self.bus, BUS, SERVICE_PATH, I_SERVICE, "Unlock", "ao", [[self.collection]])
        if self.collection not in unlocked:
            await self._prompt(prompt)

    async def _items(self, account: str | None = None) -> list[str]:
        attrs = {"application": self.app}
        if account is not None:
            attrs["account"] = account
        (items,) = await call(self.bus, BUS, self.collection, I_COLLECTION, "SearchItems", "a{ss}", [attrs])
        return items

    # --- Store ------------------------------------------------------------
    async def _load(self) -> dict[str, str]:
        await self._unlock()
        items = await self._items()
        if not items:
            return {}
        (secrets,) = await call(self.bus, BUS, SERVICE_PATH, I_SERVICE, "GetSecrets", "aoo", [items, self.session])
        out = {}
        for path in items:
            attrs = await get_prop(self.bus, BUS, path, I_ITEM, "Attributes")
            name = attrs.get("account")
            if name and path in secrets:
                out[name] = bytes(secrets[path][2]).decode("utf-8")
        return out

    async def _write(self, name: str, uri: str) -> None:
        await self._unlock()
        props = {
            f"{I_ITEM}.Label": Variant("s", f"{APP_NAME}: {name}"),
            f"{I_ITEM}.Attributes": Variant("a{ss}", {"application": self.app, "account": name, "xdg:schema": SCHEMA}),
        }
        secret = [self.session, b"", uri.encode("utf-8"), "text/plain; charset=utf8"]
        _item, prompt = await call(
            self.bus, BUS, self.collection, I_COLLECTION, "CreateItem", "a{sv}(oayays)b", [props, secret, True]
        )
        await self._prompt(prompt)

    async def _remove(self, name: str) -> bool:
        await self._unlock()
        items = await self._items(name)
        for path in items:
            (prompt,) = await call(self.bus, BUS, path, I_ITEM, "Delete")
            await self._prompt(prompt)
        return bool(items)
