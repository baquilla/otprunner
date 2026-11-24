"""Export a QR para pasar cuentas al móvil: una cuenta, su ``otpauth://`` (lo lee cualquier
app); varias, QR de migración de Google Authenticator."""

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


def build(accounts: dict[str, Account], batch_size: int = migration.DEFAULT_BATCH,
          single_otpauth: bool = True) -> Export:
    """Codifica las cuentas compatibles; las demás se listan en ``skipped``.

    Con una sola cuenta (y ``single_otpauth``) se exporta su URI ``otpauth://`` tal cual.
    """
    out = Export()
    if single_otpauth and len(accounts) == 1:
        ((name, acc),) = accounts.items()
        return Export(uris=[acc.to_uri()], exported=[name])
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


def write_sheet(uris: list[str], captions: list[str], directory: Path,
                max_width: int = 1280, max_height: int = 760) -> Path:
    """Todos los QR en una sola imagen, en rejilla y con su pie («1/2»…), del mismo tamaño."""
    import io
    import math

    import segno
    from PIL import Image, ImageDraw, ImageFont

    n = len(uris)
    cols = min(n, 3) if n <= 3 else math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    gap, caption_h = 24, 40
    size = min((max_width - gap * (cols + 1)) // cols, (max_height - (gap + caption_h) * rows - gap) // rows, 480)
    try:
        font = ImageFont.load_default(size=24)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    sheet = Image.new("RGB", (cols * size + gap * (cols + 1), rows * (size + caption_h + gap) + gap), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (uri, caption) in enumerate(zip(uris, captions)):
        buf = io.BytesIO()
        segno.make(uri, error="m").save(buf, kind="png", scale=1, border=4)
        buf.seek(0)
        qr = Image.open(buf).convert("RGB").resize((size, size), Image.NEAREST)
        x = gap + (i % cols) * (size + gap)
        y = gap + (i // cols) * (size + caption_h + gap)
        sheet.paste(qr, (x, y))
        draw.text((x + size // 2, y + size + caption_h // 2), caption, fill="black", font=font, anchor="mm")
    path = directory / f"export-{secrets.token_hex(6)}.png"
    sheet.save(path)
    path.chmod(0o600)
    return path


def terminal(uri: str) -> None:
    import segno

    segno.make(uri, error="m").terminal(compact=True)
