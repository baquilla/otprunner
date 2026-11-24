from __future__ import annotations

import abc

from ..i18n import _
from ..otpauth import Account, OtpError


class StoreError(RuntimeError):
    """Error operando con el keystore."""


class StoreUnavailable(StoreError):
    """El backend no está disponible en este sistema."""


class Store(abc.ABC):
    """Interfaz común. Los secretos se guardan como URI ``otpauth://``."""

    backend: str = ""

    @abc.abstractmethod
    async def _load(self) -> dict[str, str]:
        """Devuelve {nombre: uri} de todas las cuentas."""

    @abc.abstractmethod
    async def _write(self, name: str, uri: str) -> None: ...

    @abc.abstractmethod
    async def _remove(self, name: str) -> bool: ...

    async def close(self) -> None:  # noqa: B027
        pass

    async def describe(self) -> str:
        return self.backend

    # --- API pública ------------------------------------------------------
    async def all(self) -> dict[str, Account]:
        """Todas las cuentas válidas, ordenadas por nombre. Las corruptas se omiten."""
        out = {}
        for name, uri in sorted((await self._load()).items(), key=lambda kv: kv[0].casefold()):
            try:
                out[name] = Account.from_uri(uri)
            except OtpError:
                continue
        return out

    async def names(self) -> list[str]:
        return sorted(await self._load(), key=str.casefold)

    async def get(self, name: str) -> Account | None:
        uri = (await self._load()).get(name)
        return Account.from_uri(uri) if uri else None

    async def put(self, name: str, account: Account, *, replace: bool = False) -> None:
        name = name.strip()
        if not name:
            raise StoreError(_("the name cannot be empty"))
        if not replace and name in await self._load():
            raise StoreError(_("an account named “{name}” already exists").format(name=name))
        await self._write(name, account.to_uri())

    async def delete(self, name: str) -> bool:
        return await self._remove(name)

    async def rename(self, old: str, new: str) -> None:
        new = new.strip()
        data = await self._load()
        if old not in data:
            raise StoreError(_("the account “{name}” does not exist").format(name=old))
        if new in data:
            raise StoreError(_("an account named “{name}” already exists").format(name=new))
        await self._write(new, data[old])
        await self._remove(old)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
