"""Diálogos mínimos para el runner: kdialog → zenity. Sin herramienta, devuelven None."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from .i18n import _


class NoDialogTool(RuntimeError):
    def __init__(self) -> None:
        super().__init__(_("no dialog tool available: install kdialog or zenity"))


def tool() -> str | None:
    for t in ("kdialog", "zenity"):
        if shutil.which(t):
            return t
    return None


async def _run(cmd: list[str]) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _err = await proc.communicate()
    return proc.returncode, out.decode(errors="replace").rstrip("\n")


async def confirm(title: str, text: str, ok_label: str | None = None) -> bool:
    ok_label = ok_label or _("Continue")
    t = tool()
    if t == "kdialog":
        rc, _out = await _run(["kdialog", "--title", title, "--warningcontinuecancel", text,
                            "--continue-label", ok_label])
    elif t == "zenity":
        rc, _out = await _run(["zenity", "--question", "--title", title, "--text", text,
                            "--ok-label", ok_label, "--cancel-label", _("Cancel"), "--icon-name", "dialog-warning"])
    else:
        raise NoDialogTool()
    return rc == 0


async def ask_text(title: str, label: str, default: str = "") -> str | None:
    t = tool()
    if t == "kdialog":
        rc, out = await _run(["kdialog", "--title", title, "--inputbox", label, default])
    elif t == "zenity":
        rc, out = await _run(["zenity", "--entry", "--title", title, "--text", label, "--entry-text", default])
    else:
        raise NoDialogTool()
    return out.strip() if rc == 0 and out.strip() else None


async def show_image(path: Path, title: str) -> None:
    """Muestra la imagen y espera a que el usuario cierre la ventana."""
    t = tool()
    if t == "kdialog":
        await _run(["kdialog", "--title", title, "--imgbox", str(path)])
    elif t == "zenity" and shutil.which("xdg-open"):
        # zenity no muestra imágenes: abrimos el visor del sistema y esperamos a que el
        # usuario confirme para poder borrar el fichero.
        await _run(["xdg-open", str(path)])
        await _run(["zenity", "--info", "--title", title,
                    "--text", _("Press OK when you have scanned the QR code, and close the viewer.")])
    else:
        raise NoDialogTool()
