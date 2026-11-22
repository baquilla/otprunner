"""Flujo de alta compartido por el runner y la CLI: obtener URIs → importar → resumir."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import capture, importer
from .dbusutil import name_available
from .store import Store

SOURCES = ("screen", "clipboard")


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
            title = f"Añadida: {r.added[0]}" if len(r.added) == 1 else f"Añadidas {len(r.added)} cuentas"
            if len(r.added) > 1:
                lines.append(", ".join(r.added))
        elif r.skipped:
            title = "Nada nuevo que añadir"
        elif p.errors:
            title = "No se pudo añadir la cuenta"
        else:
            title = "No se encontró ningún código otpauth"
        for wanted, final in r.renamed:
            lines.append(f"«{wanted}» ya existía: guardada como «{final}»")
        if r.skipped:
            lines.append("Ya existían: " + ", ".join(r.skipped))
        for b in p.batches:
            if b.batch_size > 1:
                more = " — captura el siguiente QR" if b.batch_index + 1 < b.batch_size else ""
                lines.append(f"Exportación de Google: lote {b.batch_index + 1} de {b.batch_size}{more}")
        lines.extend(p.errors)
        if self.ok:
            lines.extend(self.notes)
        return title, "\n".join(lines)


async def acquire(source: str, bus, *, uri: str | None = None) -> tuple[importer.Parsed, list[str]]:
    """Devuelve las cuentas encontradas y avisos para el usuario."""
    if source == "uri":
        return importer.parse_text(uri or ""), []
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
            notes.append("La URI con el secreto sigue en el historial de Klipper: bórrala desde su menú.")
        return parsed, notes
    raise ValueError(f"origen desconocido: {source}")


async def add(store: Store, source: str, bus, *, name: str | None = None, uri: str | None = None) -> Outcome:
    parsed, notes = await acquire(source, bus, uri=uri)
    out = Outcome(parsed, notes=notes)
    if parsed.accounts:
        out.result = await importer.import_accounts(store, parsed.accounts, name=name or None)
    return out
