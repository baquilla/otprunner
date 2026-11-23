"""Flujo de alta compartido por el runner y la CLI: obtener URIs → importar → resumir."""

from __future__ import annotations

from dataclasses import dataclass, field

from collections.abc import Callable

from . import camera, capture, importer
from .dbusutil import name_available
from .i18n import _, ngettext
from .store import Store

SOURCES = ("screen", "clipboard", "camera")


@dataclass
class Outcome:
    parsed: importer.Parsed
    result: importer.ImportResult = field(default_factory=importer.ImportResult)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.result.added or self.result.skipped)

    def summary(self) -> tuple[str, str]:
        """(título, cuerpo) para notificación o consola."""
        r, p = self.result, self.parsed
        lines = []
        if r.added:
            if len(r.added) == 1:
                title = _("Added: {name}").format(name=r.added[0])
            else:
                title = ngettext("Added {n} account", "Added {n} accounts", len(r.added)).format(n=len(r.added))
            if len(r.added) > 1:
                lines.append(", ".join(r.added))
        elif r.skipped:
            title = _("Nothing new to add")
        elif p.errors:
            title = _("Could not add the account")
        else:
            title = _("No otpauth code found")
        for wanted, final in r.renamed:
            lines.append(_("“{wanted}” already existed: saved as “{final}”").format(wanted=wanted, final=final))
        if r.skipped:
            lines.append(_("Already present: {names}").format(names=", ".join(r.skipped)))
        for b in p.batches:
            if b.batch_size > 1:
                if b.batch_index + 1 < b.batch_size:
                    msg = _("Google export: batch {i} of {n} — capture the next QR code")
                else:
                    msg = _("Google export: batch {i} of {n}")
                lines.append(msg.format(i=b.batch_index + 1, n=b.batch_size))
        lines.extend(p.errors)
        if self.ok:
            lines.extend(self.notes)
        return title, "\n".join(lines)


async def acquire(source: str, bus, *, uri: str | None = None, device: str | None = None,
                  progress: Callable[[str], None] | None = None) -> tuple[importer.Parsed, list[str]]:
    """Devuelve las cuentas encontradas y avisos para el usuario."""
    if source == "uri":
        return importer.parse_text(uri or ""), []
    if source == "camera":
        texts = await camera.scan(device, progress)
        if not texts:
            raise capture.CaptureCancelled("cancelled")
        return importer.parse_text("\n".join(texts)), []
    if source == "screen":
        return importer.parse_text("\n".join(await capture.from_screen(bus))), []
    if source == "clipboard":
        parsed = importer.parse_text(await capture.clipboard_text(bus))
        if not parsed.accounts and not parsed.errors:
            return importer.parse_text("\n".join(await capture.clipboard_image_qr())), []
        notes = []
        # Klipper no permite borrar una entrada concreta del historial (ni vaciar el
        # portapapeles si «evitar portapapeles vacío» está activo): solo podemos avisar.
        if parsed.accounts and bus is not None and await name_available(bus, "org.kde.klipper"):
            notes.append(_("The URI with the secret is still in the Klipper history: delete it from its menu."))
        return parsed, notes
    raise ValueError(f"unknown source: {source}")


async def add(store: Store, source: str, bus, *, name: str | None = None, uri: str | None = None,
              device: str | None = None, progress: Callable[[str], None] | None = None) -> Outcome:
    parsed, notes = await acquire(source, bus, uri=uri, device=device, progress=progress)
    out = Outcome(parsed, notes=notes)
    if parsed.accounts:
        out.result = await importer.import_accounts(store, parsed.accounts, name=name or None)
    return out
