"""Export a QR de migración (Google Authenticator) para pasar cuentas al móvil."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path

from . import migration
from .otpauth import Account, OtpError


@dataclass
class Export:
    uris: list[str] = field(default_factory=list)
    exported: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (nombre, motivo)


def build(accounts: dict[str, Account], batch_size: int = migration.DEFAULT_BATCH) -> Export:
    """Codifica las cuentas compatibles; las demás se listan en ``skipped``."""
    out = Export()
    ok: list[Account] = []
    for name, acc in accounts.items():
        try:
            migration.encode([acc])  # valida (periodo 30 s, 6/8 dígitos)
        except OtpError as e:
            out.skipped.append((name, str(e).split(": ", 1)[-1]))
            continue
        ok.append(acc)
        out.exported.append(name)
    out.uris = migration.encode(ok, batch_size=batch_size)
    return out


def write_png(uri: str, directory: Path, scale: int = 6) -> Path:
    import segno

    path = directory / f"export-{secrets.token_hex(6)}.png"
    segno.make(uri, error="m").save(str(path), scale=scale, border=4)
    path.chmod(0o600)
    return path


def terminal(uri: str) -> None:
    import segno

    segno.make(uri, error="m").terminal(compact=True)
