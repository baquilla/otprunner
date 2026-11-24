"""Cuentas ficticias para demostraciones y capturas (``otprunner serve --demo``)."""

from __future__ import annotations

import secrets

from .otpauth import Account
from .store import MemoryStore

ACCOUNTS = (
    ("GitHub", "alice"),
    ("GitLab", "alice"),
    ("Google", "alice@example.com"),
    ("Proton", "alice@proton.me"),
    ("Amazon", "alice@example.com"),
    ("AWS", "alice (root)"),
    ("Cloudflare", "alice@example.com"),
    ("Dropbox", "alice@example.com"),
    ("Mastodon", "@alice@fosstodon.org"),
    ("Nextcloud", "alice"),
    ("PayPal", "alice@example.com"),
    ("Bitwarden", "alice@example.com"),
    ("Discord", "alice#4242"),
    ("DigitalOcean", "alice@example.com"),
)


def store() -> MemoryStore:
    """Almacén en memoria con secretos aleatorios: nada de esto existe fuera del proceso."""
    s = MemoryStore()
    for issuer, name in ACCOUNTS:
        acc = Account(secret=secrets.token_bytes(20), name=name, issuer=issuer)
        s.data[acc.label] = acc.to_uri()
    return s
