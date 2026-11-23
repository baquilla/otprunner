"""Lectura de QR con la cámara: zbarcam → OpenCV (opcional: ``pipx inject otprunner opencv-python``).

La cámara sigue abierta hasta leer un QR otpauth://, o todos los lotes de una
exportación de Google (avisando del progreso), o hasta que el usuario cierra la ventana.
"""

from __future__ import annotations

import asyncio
import glob
import importlib.util
import logging
import shutil
from collections.abc import Callable

from . import APP_NAME, migration
from .otpauth import OtpError

log = logging.getLogger(__name__)

SCAN_TIMEOUT = 180
WINDOW_TITLE = f"{APP_NAME}: enseña el QR a la cámara (Esc o cerrar para cancelar)"


class CameraError(RuntimeError):
    pass


def devices() -> list[str]:
    return sorted(glob.glob("/dev/video*"), key=lambda d: int(d.removeprefix("/dev/video") or 0))


def providers() -> list[str]:
    out = []
    if shutil.which("zbarcam"):
        out.append("zbarcam")
    if importlib.util.find_spec("cv2") is not None:
        out.append("opencv")
    return out


def install_hint() -> str:
    if shutil.which("apt"):
        pkg = "sudo apt install zbar-tools"
    elif shutil.which("dnf"):
        pkg = "sudo dnf install zbar"
    elif shutil.which("pacman"):
        pkg = "sudo pacman -S zbar"
    else:
        pkg = "instala zbar (zbarcam)"
    return f"{pkg}  —  o bien: pipx inject otprunner opencv-python"


class Collector:
    """Acumula lecturas hasta tener algo completo que importar."""

    def __init__(self, progress: Callable[[str], None] | None = None) -> None:
        self.texts: list[str] = []
        self._seen: set[str] = set()
        self._batches: dict[int, set[int]] = {}
        self._sizes: dict[int, int] = {}
        self.progress = progress or (lambda msg: None)
        self.done = False

    def feed(self, text: str) -> bool:
        text = text.strip()
        if not text or text in self._seen:
            return self.done
        self._seen.add(text)
        low = text.lower()
        if low.startswith("otpauth://"):
            self.texts.append(text)
            self.done = True
        elif low.startswith("otpauth-migration://"):
            try:
                b = migration.decode(text)
            except OtpError as e:
                log.info("QR de migración no válido: %s", e)
                return self.done
            self.texts.append(text)
            got = self._batches.setdefault(b.batch_id, set())
            got.add(b.batch_index)
            self._sizes[b.batch_id] = b.batch_size
            if len(got) >= b.batch_size:
                self.done = True
            else:
                self.progress(f"Lote {b.batch_index + 1} de {b.batch_size} leído "
                              f"({len(got)}/{b.batch_size}): enseña el siguiente QR")
        else:
            log.info("QR ignorado: no es otpauth")
        return self.done


async def _zbarcam(device: str | None, col: Collector) -> None:
    # Salida normal («QR-Code:<datos>\n»): --raw no garantiza un salto de línea por lectura.
    cmd = ["zbarcam", "-q", "--nodbus", "-Sdisable", "-Sqrcode.enable"]
    if device:
        cmd.append(device)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            _, sep, data = text.partition(":")
            if sep and _.replace("-", "").isalnum() and not _.lower().startswith("otpauth"):
                text = data  # quitar el prefijo de simbología («QR-Code:»)
            if col.feed(text):
                break
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                proc.kill()
        try:
            err = (await asyncio.wait_for(proc.stderr.read(), 2)).decode(errors="replace").strip()
        except asyncio.TimeoutError:  # algún hijo mantiene stderr abierto
            err = ""
    if proc.returncode not in (0, None, -15) and not col.texts:
        raise CameraError(f"zbarcam falló ({proc.returncode}): {err.splitlines()[-1] if err else 'sin detalle'}")


def _opencv_blocking(device: str | None, col: Collector, deadline: float) -> None:
    import time

    import cv2
    import zxingcpp

    idx = int(device.removeprefix("/dev/video")) if device else 0
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        raise CameraError(f"no se pudo abrir la cámara {device or idx}")
    try:
        cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
        while time.monotonic() < deadline:
            ok, frame = cap.read()
            if not ok:
                raise CameraError("la cámara no devuelve imágenes")
            cv2.imshow(WINDOW_TITLE, frame)
            for r in zxingcpp.read_barcodes(frame, formats=zxingcpp.BarcodeFormat.QRCode):
                if r.text and col.feed(r.text):
                    return
            key = cv2.waitKey(30) & 0xFF
            if key == 27 or cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return
    finally:
        cap.release()
        cv2.destroyAllWindows()


async def scan(device: str | None = None, progress: Callable[[str], None] | None = None,
               timeout: float = SCAN_TIMEOUT) -> list[str]:
    """Devuelve los textos otpauth leídos (vacío si el usuario cerró sin leer nada)."""
    provs = providers()
    if not provs:
        raise CameraError("no hay lector de QR para la cámara: " + install_hint())
    if not devices():
        raise CameraError("no se ha encontrado ninguna cámara (/dev/video*)")
    col = Collector(progress)
    prov = provs[0]
    log.info("leyendo QR con %s (%s)", prov, device or "cámara por defecto")
    try:
        if prov == "zbarcam":
            await asyncio.wait_for(_zbarcam(device, col), timeout)
        else:
            import time

            loop = asyncio.get_running_loop()
            # El progreso llega desde el hilo de OpenCV: reencaminarlo al bucle.
            if progress:
                col.progress = lambda msg: loop.call_soon_threadsafe(progress, msg)
            # El plazo se comprueba dentro del hilo: cancelar el future no liberaría la cámara.
            await loop.run_in_executor(None, _opencv_blocking, device, col, time.monotonic() + timeout)
    except asyncio.TimeoutError:
        if not col.texts:
            raise CameraError("tiempo agotado sin leer ningún QR") from None
    return col.texts
