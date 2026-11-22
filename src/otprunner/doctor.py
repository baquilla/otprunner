"""Diagnóstico del entorno: qué keystore y herramientas hay y cuáles se usarían."""

from __future__ import annotations

import os
import platform
import shutil
import sys

from . import __version__, camera, config
from .dbusutil import name_available, session_bus
from .store import BACKENDS, StoreUnavailable, kwallet, secretservice

OK, NO, WARN = "✔", "✘", "!"


def _env() -> list[tuple[str, str]]:
    return [
        ("otprunner", __version__),
        ("Python", f"{platform.python_version()} ({sys.executable})"),
        ("Sesión", os.environ.get("XDG_SESSION_TYPE", "?")),
        ("Escritorio", os.environ.get("XDG_CURRENT_DESKTOP", "?")),
        ("Plasma", os.environ.get("KDE_SESSION_VERSION", "no")),
        ("Config", str(config.config_path()) + ("" if config.config_path().exists() else " (no existe, valores por defecto)")),
    ]


async def run() -> int:
    cfg = config.load()
    for k, v in _env():
        print(f"{k:12} {v}")
    print()

    bus = await session_bus()
    rc = 0
    try:
        # --- keystore --------------------------------------------------------
        print(f"Keystore (backend = {cfg.backend})")
        impl = {"secretservice": secretservice.SecretServiceStore, "kwallet": kwallet.KWalletStore}
        chosen = None
        for name in BACKENDS:
            try:
                st = await impl[name].open(bus=bus)
                desc = await st.describe()
                await st.close()
                usable = cfg.backend in ("auto", name)
                mark = "  ← en uso" if usable and chosen is None else ""
                if usable and chosen is None:
                    chosen = name
                print(f"  {OK} {name:14} {desc}{mark}")
            except StoreUnavailable as e:
                print(f"  {NO} {name:14} {e}")
        if chosen is None:
            print(f"  {NO} ningún keystore utilizable: instala/activa KWallet, GNOME Keyring o KeePassXC")
            rc = 1
        print()

        # --- herramientas ----------------------------------------------------
        async def dbus(name: str) -> bool:
            return await name_available(bus, name)

        def bin_(name: str) -> bool:
            return shutil.which(name) is not None

        wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
        groups = [
            ("KRunner", [("org.kde.krunner (DBus)", await dbus("org.kde.krunner"))], "solo en KDE Plasma"),
            (
                "Portapapeles",
                [
                    ("Klipper (DBus)", await dbus("org.kde.klipper")),
                    ("wl-copy", wayland and bin_("wl-copy")),
                    ("xclip", not wayland and bin_("xclip")),
                    ("xsel", not wayland and bin_("xsel")),
                ],
                "instala wl-clipboard (Wayland) o xclip (X11)",
            ),
            (
                "Captura",
                [
                    ("spectacle", bin_("spectacle")),
                    ("portal XDG Screenshot", await dbus("org.freedesktop.portal.Desktop")),
                    ("gnome-screenshot", not wayland and bin_("gnome-screenshot")),
                    ("maim", not wayland and bin_("maim")),
                ],
                "instala xdg-desktop-portal-kde/-gnome o spectacle",
            ),
            (
                "Cámara (" + (", ".join(camera.devices()) or "sin dispositivos /dev/video*") + ")",
                [("zbarcam", bin_("zbarcam")), ("opencv", "opencv" in camera.providers())],
                camera.install_hint(),
            ),
            (
                "Diálogos",
                [("kdialog", bin_("kdialog")), ("zenity", bin_("zenity"))],
                "instala kdialog o zenity",
            ),
            (
                "Notificaciones",
                [("org.freedesktop.Notifications", await dbus("org.freedesktop.Notifications"))],
                "sin notificaciones los errores solo irán al journal",
            ),
        ]
        from . import install

        print("Instalación")
        for key, path in install.paths().items():
            print(f"  {OK if path.exists() else NO} {key:8} {path}")
        if not install.paths()["runner"].exists():
            print(f"  {WARN} ejecuta «otprunner install» para registrar el runner")
        for old in install.legacy_paths():
            if old.exists():
                print(f"  {WARN} resto de la versión antigua: {old} (lo borra «otprunner install»)")

        for title, provs, hint in groups:
            print(title)
            first = next((n for n, ok in provs if ok), None)
            for n, ok in provs:
                print(f"  {OK if ok else NO} {n}{'  ← en uso' if n == first else ''}")
            if first is None:
                print(f"  {WARN} {hint}")
        return rc
    finally:
        bus.disconnect()
