"""Diálogos mínimos para el runner: kdialog → zenity. Sin herramienta, devuelven None."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
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


_MONITOR_RE = re.compile(r"(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)")
# Espacio que se quedan la barra de título, los botones del visor y el panel del escritorio.
_CHROME_W, _CHROME_H = 80, 160


def _out(cmd: list[str]) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def monitors(listing: str | None = None) -> list[tuple[int, int, int, int]]:
    """(ancho, alto, x, y) de cada monitor, según ``xrandr --listmonitors`` (X11 y XWayland)."""
    text = _out(["xrandr", "--listmonitors"]) if listing is None else listing
    return [tuple(map(int, m.groups())) for m in _MONITOR_RE.finditer(text)]  # type: ignore[misc]


def pointer(text: str | None = None) -> tuple[int, int] | None:
    text = _out(["xdotool", "getmouselocation", "--shell"]) if text is None else text
    xy = dict(re.findall(r"^([XY])=(-?\d+)$", text, re.M))
    return (int(xy["X"]), int(xy["Y"])) if len(xy) == 2 else None


def image_area(default: tuple[int, int] = (1280, 760), mons=None, ptr=None) -> tuple[int, int]:
    """Tamaño máximo de una imagen para que su ventana quepa en pantalla.

    Usa el monitor donde está el puntero (donde KDE abre las ventanas nuevas); si no se
    sabe, el más pequeño, para que quepa en cualquiera.
    """
    mons = monitors() if mons is None else mons
    if not mons:
        return default
    ptr = pointer() if ptr is None else ptr
    here = [m for m in mons if ptr and m[2] <= ptr[0] < m[2] + m[0] and m[3] <= ptr[1] < m[3] + m[1]]
    w, h, _x, _y = here[0] if here else min(mons, key=lambda m: m[0] * m[1])
    return max(min(w - _CHROME_W, default[0]), 200), max(min(h - _CHROME_H, default[1]), 200)


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
