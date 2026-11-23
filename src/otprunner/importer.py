"""Extracción de cuentas de texto libre (otpauth:// y otpauth-migration://) y alta en el almacén."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import migration
from .otpauth import Account, OtpError
from .i18n import _
from .store import Store

_URI_RE = re.compile(r"otpauth(?:-migration)?://[^\s\"'<>]+", re.IGNORECASE)


@dataclass
class Parsed:
    accounts: list[Account] = field(default_factory=list)
    batches: list[migration.Batch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_text(text: str) -> Parsed:
    """Busca todas las URIs OTP en ``text``. Los errores no abortan el resto."""
    out = Parsed()
    for uri in _URI_RE.findall(text):
        try:
            if migration.is_migration_uri(uri):
                batch = migration.decode(uri)
                out.batches.append(batch)
                out.accounts.extend(batch.accounts)
            else:
                out.accounts.append(Account.from_uri(uri))
        except OtpError as e:
            out.errors.append(f"{uri[:40]}…: {e}")
    return out


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # mismo secreto ya presente
    renamed: list[tuple[str, str]] = field(default_factory=list)  # (deseado, asignado)


def _unique(name: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    n = 2
    while f"{name} ({n})" in taken:
        n += 1
    return f"{name} ({n})"


async def import_accounts(store: Store, accounts: list[Account], name: str | None = None) -> ImportResult:
    """Da de alta ``accounts``.

    - Si ya existe una cuenta con el mismo secreto (y tipo), se omite.
    - Si el nombre está ocupado por otra cuenta, se añade un sufijo « (n)».
    - ``name`` solo se usa si hay una única cuenta.
    """
    if name and len(accounts) != 1:
        name = None
    existing = await store.all()
    known = {(a.secret, a.type) for a in existing.values()}
    taken = set(existing)
    res = ImportResult()
    for acc in accounts:
        wanted = (name or acc.label or _("unnamed")).strip()
        if (acc.secret, acc.type) in known:
            res.skipped.append(wanted)
            continue
        final = _unique(wanted, taken)
        await store.put(final, acc)
        taken.add(final)
        known.add((acc.secret, acc.type))
        res.added.append(final)
        if final != wanted:
            res.renamed.append((wanted, final))
    return res
