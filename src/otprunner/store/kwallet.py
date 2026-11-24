"""Backend KWallet nativo (org.kde.kwalletd5/6), para KDE sin Secret Service (KF < 5.97).

Las cuentas se guardan como «passwords» en la carpeta ``<app>`` del monedero de red.
"""

from __future__ import annotations

from ..dbusutil import DBusCallError, call, name_available, session_bus
from ..i18n import _
from .base import Store, StoreError, StoreUnavailable

IFACE = "org.kde.KWallet"
DAEMONS = (("org.kde.kwalletd6", "/modules/kwalletd6"), ("org.kde.kwalletd5", "/modules/kwalletd5"))


class KWalletStore(Store):
    backend = "kwallet"

    def __init__(self, bus, app: str, owns_bus: bool, dest: str, path: str) -> None:
        self.bus, self.app, self._owns_bus = bus, app, owns_bus
        self.dest, self.path = dest, path
        self.folder = app
        self.wallet = ""
        self.handle = -1

    @classmethod
    async def open(cls, app: str = "otprunner", bus=None) -> KWalletStore:
        owns = bus is None
        bus = bus or await session_bus()
        try:
            for dest, path in DAEMONS:
                if await name_available(bus, dest):
                    self = cls(bus, app, owns, dest, path)
                    (self.wallet,) = await self._call("networkWallet")
                    return self
            raise StoreUnavailable(_("kwalletd is not on the session bus"))
        except DBusCallError as e:
            if owns:
                bus.disconnect()
            raise StoreUnavailable(str(e)) from None
        except BaseException:
            if owns:
                bus.disconnect()
            raise

    async def _call(self, member: str, sig: str = "", body=None):
        return await call(self.bus, self.dest, self.path, IFACE, member, sig, body)

    async def describe(self) -> str:
        return _("native KWallet ({service}), wallet “{wallet}”, folder “{folder}”").format(
            service=self.dest, wallet=self.wallet, folder=self.folder
        )

    async def close(self) -> None:
        if self._owns_bus:
            self.bus.disconnect()

    async def _open(self) -> int:
        if self.handle >= 0:
            (ok,) = await self._call("isOpen", "i", [self.handle])
            if ok:
                return self.handle
        # Puede mostrar el diálogo de contraseña; dbus-fast espera sin timeout.
        (self.handle,) = await self._call("open", "sxs", [self.wallet, 0, self.app])
        if self.handle < 0:
            raise StoreError(_("could not open the wallet (cancelled?)"))
        (has,) = await self._call("hasFolder", "iss", [self.handle, self.folder, self.app])
        if not has:
            await self._call("createFolder", "iss", [self.handle, self.folder, self.app])
        return self.handle

    async def _load(self) -> dict[str, str]:
        h = await self._open()
        (entries,) = await self._call("readPasswordList", "isss", [h, self.folder, "*", self.app])
        return {k: v.value for k, v in entries.items()}

    async def _write(self, name: str, uri: str) -> None:
        h = await self._open()
        (rc,) = await self._call("writePassword", "issss", [h, self.folder, name, uri, self.app])
        if rc != 0:
            raise StoreError(_("KWallet writePassword returned {rc}").format(rc=rc))

    async def _remove(self, name: str) -> bool:
        h = await self._open()
        (has,) = await self._call("hasEntry", "isss", [h, self.folder, name, self.app])
        if not has:
            return False
        (rc,) = await self._call("removeEntry", "isss", [h, self.folder, name, self.app])
        return rc == 0
