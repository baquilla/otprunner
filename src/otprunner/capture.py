"""Obtención de URIs OTP desde una captura de pantalla o el portapapeles.

Captura: spectacle (región) → portal XDG Screenshot (interactivo; vale en Wayland) →
gnome-screenshot → maim. Las imágenes contienen secretos: se escriben en
``$XDG_RUNTIME_DIR/otprunner`` (tmpfs, 0700) y se borran siempre, incluida la que
haya guardado el portal donde sea.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dbus_fast import Message, MessageType, Variant

from .dbusutil import DBusCallError, call, name_available
from .i18n import _

log = logging.getLogger(__name__)

CAPTURE_TIMEOUT = 180  # el usuario tiene que seleccionar la zona


class CaptureError(RuntimeError):
    pass


class CaptureCancelled(CaptureError):
    pass


class NoQRFound(CaptureError):
    pass


def private_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    d = Path(base) / "otprunner"
    d.mkdir(mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    return d


# --- decodificación -------------------------------------------------------------
def decode_qr(path: Path) -> list[str]:
    """Textos de todos los QR de la imagen."""
    import zxingcpp
    from PIL import Image

    with Image.open(path) as img:
        img.load()
        results = zxingcpp.read_barcodes(img)
        if not results:  # QR pequeños o con poco contraste: probar ampliado y en grises
            big = img.convert("L").resize((img.width * 2, img.height * 2))
            results = zxingcpp.read_barcodes(big)
    return [r.text for r in results if r.text]


# --- captura ------------------------------------------------------------------
async def _run(cmd: list[str], timeout: float = CAPTURE_TIMEOUT) -> int:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise CaptureError(_("{tool}: timed out").format(tool=cmd[0])) from None
    if proc.returncode:
        log.debug("%s rc=%s: %s", cmd[0], proc.returncode, err.decode(errors="replace").strip())
    return proc.returncode


def _x11() -> bool:
    return bool(os.environ.get("DISPLAY")) and not os.environ.get("WAYLAND_DISPLAY")


async def _portal(bus, out: Path) -> Path:
    """org.freedesktop.portal.Screenshot interactivo. Devuelve la ruta que haya elegido el portal."""
    token = "otprunner" + secrets.token_hex(4)
    sender = bus.unique_name.lstrip(":").replace(".", "_")
    req_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    def handler(msg: Message):
        if (
            msg.message_type == MessageType.SIGNAL
            and msg.path == req_path
            and msg.member == "Response"
            and not fut.done()
        ):
            fut.set_result(msg.body)

    rule = f"type='signal',interface='org.freedesktop.portal.Request',member='Response',path='{req_path}'"
    await call(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "AddMatch", "s", [rule])
    bus.add_message_handler(handler)
    try:
        await call(
            bus,
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            "sa{sv}",
            ["", {"handle_token": Variant("s", token), "interactive": Variant("b", True)}],
        )
        code, results = await asyncio.wait_for(fut, CAPTURE_TIMEOUT)
    except asyncio.TimeoutError:
        raise CaptureError(_("{tool}: timed out").format(tool="portal")) from None
    finally:
        bus.remove_message_handler(handler)
    if code == 1:
        raise CaptureCancelled("cancelled")
    if code != 0 or "uri" not in results:
        raise CaptureError(_("the portal returned no screenshot (code {code})").format(code=code))
    parts = urlsplit(results["uri"].value)
    return Path(unquote(parts.path))


async def providers(bus) -> list[str]:
    out = []
    if shutil.which("spectacle"):
        out.append("spectacle")
    if bus is not None and await name_available(bus, "org.freedesktop.portal.Desktop"):
        out.append("portal")
    if _x11() and shutil.which("gnome-screenshot"):
        out.append("gnome-screenshot")
    if _x11() and shutil.which("maim"):
        out.append("maim")
    return out


async def screenshot(bus, provider: str, out: Path) -> Path:
    """Captura una zona elegida por el usuario. Devuelve la ruta de la imagen."""
    if provider == "portal":
        return await _portal(bus, out)
    cmd = {
        "spectacle": ["spectacle", "-b", "-n", "-r", "-o", str(out)],
        "gnome-screenshot": ["gnome-screenshot", "-a", "-f", str(out)],
        "maim": ["maim", "-s", str(out)],
    }[provider]
    rc = await _run(cmd)
    if not out.exists() or out.stat().st_size == 0:
        raise (
            CaptureCancelled("cancelled")
            if rc in (0, 1)
            else CaptureError(_("{tool}: exit code {rc}").format(tool=provider, rc=rc))
        )
    return out


async def from_screen(bus, delay: float = 0.4) -> list[str]:
    """Pide al usuario una zona de pantalla y devuelve los textos de los QR que haya."""
    provs = await providers(bus)
    if not provs:
        raise CaptureError(_("no screen capture tool: install spectacle or xdg-desktop-portal"))
    await asyncio.sleep(delay)  # que KRunner termine de cerrarse
    out = private_dir() / f"capture-{secrets.token_hex(6)}.png"
    errors = []
    for prov in provs:
        img = None
        try:
            img = await screenshot(bus, prov, out)
            texts = await asyncio.get_running_loop().run_in_executor(None, decode_qr, img)
            if not texts:
                raise NoQRFound(_("no QR code detected in the captured area"))
            return texts
        except (CaptureCancelled, NoQRFound):
            raise
        except CaptureError as e:
            errors.append(f"{prov}: {e}")
        except (OSError, DBusCallError) as e:
            errors.append(f"{prov}: {e}")
        finally:
            for p in {out, img} - {None}:
                try:
                    p.unlink(missing_ok=True)
                except OSError as e:
                    log.warning("could not delete %s: %s", p, e)
    raise CaptureError("; ".join(errors))


# --- portapapeles ---------------------------------------------------------------
async def _read_cmd(cmd: list[str]) -> bytes | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        data, _err = await asyncio.wait_for(proc.communicate(), 5)
        return data if proc.returncode == 0 and data else None
    except (OSError, asyncio.TimeoutError):
        return None


async def clipboard_text(bus) -> str:
    if bus is not None:
        try:
            if await name_available(bus, "org.kde.klipper"):
                (txt,) = await call(
                    bus, "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "getClipboardContents"
                )
                if txt:
                    return txt
        except DBusCallError:
            pass
    for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-bo"]):
        if cmd[0] == "wl-paste" and not os.environ.get("WAYLAND_DISPLAY"):
            continue
        data = await _read_cmd(cmd)
        if data:
            return data.decode(errors="replace")
    return ""


async def clipboard_image_qr() -> list[str]:
    """QR de una imagen copiada al portapapeles (p. ej. «copiar imagen» en el navegador)."""
    cmds = []
    if os.environ.get("WAYLAND_DISPLAY"):
        cmds.append(["wl-paste", "-t", "image/png"])
    if os.environ.get("DISPLAY"):
        cmds.append(["xclip", "-selection", "clipboard", "-t", "image/png", "-o"])
    for cmd in cmds:
        data = await _read_cmd(cmd)
        if not data:
            continue
        path = private_dir() / f"clip-{secrets.token_hex(6)}.png"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            return await asyncio.get_running_loop().run_in_executor(None, decode_qr, path)
        except OSError:
            continue
        finally:
            path.unlink(missing_ok=True)
    return []
