"""Copia al portapapeles con el primer proveedor disponible: Klipper → wl-copy → xclip → xsel."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

from .dbusutil import DBusCallError, call, name_available
from .i18n import _

log = logging.getLogger(__name__)


class ClipboardError(RuntimeError):
    pass


def _commands() -> list[tuple[str, list[str]]]:
    cmds = []
    if os.environ.get("WAYLAND_DISPLAY"):
        cmds.append(("wl-copy", ["wl-copy"]))
    if os.environ.get("DISPLAY"):
        cmds.append(("xclip", ["xclip", "-selection", "clipboard", "-in"]))
        cmds.append(("xsel", ["xsel", "--clipboard", "--input"]))
    return [(n, c) for n, c in cmds if shutil.which(c[0])]


async def providers(bus) -> list[str]:
    out = ["klipper"] if bus is not None and await name_available(bus, "org.kde.klipper") else []
    return out + [n for n, _ in _commands()]


async def copy(text: str, bus=None) -> str:
    """Copia ``text`` y devuelve el nombre del proveedor usado."""
    errors = []
    if bus is not None:
        try:
            if await name_available(bus, "org.kde.klipper"):
                await call(
                    bus, "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "setClipboardContents", "s", [text]
                )
                return "klipper"
        except DBusCallError as e:
            errors.append(f"klipper: {e}")
    for name, cmd in _commands():
        try:
            # xclip/xsel/wl-copy se quedan en segundo plano sirviendo la selección:
            # no capturamos su salida para no esperar a que terminen.
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            proc.stdin.write(text.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            rc = await asyncio.wait_for(proc.wait(), timeout=5)
            if rc == 0:
                return name
            errors.append(_("{tool}: exit code {rc}").format(tool=name, rc=rc))
        except (OSError, asyncio.TimeoutError) as e:
            errors.append(f"{name}: {e}")
    if errors:
        raise ClipboardError(_("no clipboard available: {errors}").format(errors="; ".join(errors)))
    raise ClipboardError(_("no clipboard available (install wl-clipboard or xclip)"))
