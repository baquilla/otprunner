"""Almacenes de secretos. Cada cuenta se guarda bajo un nombre único elegido por el usuario."""

from __future__ import annotations

from ..otpauth import Account
from ..i18n import _
from .base import Store, StoreError, StoreUnavailable
from .memory import MemoryStore

__all__ = ["Account", "MemoryStore", "Store", "StoreError", "StoreUnavailable", "open_store", "BACKENDS"]

# KWallet nativo primero: guarda todo en una carpeta propia del monedero. Su puente
# Secret Service mezcla los items en la carpeta «Secret Service» y trata «/» de la
# etiqueta como separador de carpetas.
BACKENDS = ("kwallet", "secretservice")


async def open_store(backend: str = "auto", app: str = "otprunner", bus=None) -> Store:
    """Abre el primer backend disponible (o el indicado)."""
    from . import kwallet, secretservice

    impl = {"secretservice": secretservice.SecretServiceStore, "kwallet": kwallet.KWalletStore}
    order = BACKENDS if backend == "auto" else (backend,)
    reasons = []
    for name in order:
        if name not in impl:
            raise StoreError(_("unknown backend: {name} (valid: auto, {valid})").format(name=name, valid=", ".join(BACKENDS)))
        try:
            return await impl[name].open(app=app, bus=bus)
        except StoreUnavailable as e:
            reasons.append(f"{name}: {e}")
    raise StoreUnavailable(_("no keystore available:") + "\n  " + "\n  ".join(reasons))
