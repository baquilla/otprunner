"""Diagnóstico del entorno: qué keystore y herramientas hay y cuáles se usarían."""

from __future__ import annotations

import os
import platform
import shutil
import sys

from . import APP_NAME, __version__, camera, config, i18n
from .dbusutil import NoSessionBus, name_available, session_bus
from .i18n import _
from .store import BACKENDS, StoreUnavailable, kwallet, secretservice

OK, NO, WARN = "✔", "✘", "!"


def i18n_status() -> str:
    t = i18n._translations()
    lang = (t.info().get("language") or "?") if type(t).__name__ != "NullTranslations" else "en"
    return _("{current} (available: {langs})").format(current=lang, langs=", ".join(["en", *i18n.available()]))


def _env() -> list[tuple[str, str]]:
    return [
        (APP_NAME, __version__),
        ("Python", f"{platform.python_version()} ({sys.executable})"),
        (_("Session"), os.environ.get("XDG_SESSION_TYPE", "?")),
        (_("Desktop"), os.environ.get("XDG_CURRENT_DESKTOP", "?")),
        ("Plasma", os.environ.get("KDE_SESSION_VERSION", _("no"))),
        (_("Config"), str(config.config_path()) + ("" if config.config_path().exists() else " " + _("(missing, using defaults)"))),
        (_("Language"), i18n_status()),
    ]


async def run() -> int:
    cfg = config.load()
    for k, v in _env():
        print(f"{k:14} {v}")
    print()

    try:
        bus = await session_bus()
    except NoSessionBus as e:
        print(f"{NO} {e}")
        return 1
    rc = 0
    try:
        # --- keystore --------------------------------------------------------
        print(_("Keystore (backend = {backend})").format(backend=cfg.backend))
        impl = {"secretservice": secretservice.SecretServiceStore, "kwallet": kwallet.KWalletStore}  # orden: BACKENDS
        chosen = None
        for name in BACKENDS:
            try:
                st = await impl[name].open(bus=bus)
                desc = await st.describe()
                await st.close()
                usable = cfg.backend in ("auto", name)
                mark = "  ← " + _("in use") if usable and chosen is None else ""
                if usable and chosen is None:
                    chosen = name
                print(f"  {OK} {name:14} {desc}{mark}")
            except StoreUnavailable as e:
                print(f"  {NO} {name:14} {e}")
        if chosen is None:
            print(f"  {NO} " + _("no usable keystore: install/enable KWallet, GNOME Keyring or KeePassXC"))
            rc = 1
        print()

        # --- herramientas ----------------------------------------------------
        async def dbus(name: str) -> bool:
            return await name_available(bus, name)

        def bin_(name: str) -> bool:
            return shutil.which(name) is not None

        wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
        groups = [
            ("KRunner", [("org.kde.krunner (DBus)", await dbus("org.kde.krunner"))], _("KDE Plasma only")),
            (
                _("Clipboard"),
                [
                    ("Klipper (DBus)", await dbus("org.kde.klipper")),
                    ("wl-copy", wayland and bin_("wl-copy")),
                    ("xclip", not wayland and bin_("xclip")),
                    ("xsel", not wayland and bin_("xsel")),
                ],
                _("install wl-clipboard (Wayland) or xclip (X11)"),
            ),
            (
                _("Screen capture"),
                [
                    ("spectacle", bin_("spectacle")),
                    (_("XDG Screenshot portal"), await dbus("org.freedesktop.portal.Desktop")),
                    ("gnome-screenshot", not wayland and bin_("gnome-screenshot")),
                    ("maim", not wayland and bin_("maim")),
                ],
                _("install xdg-desktop-portal-kde/-gnome or spectacle"),
            ),
            (
                _("Camera ({devices})").format(devices=", ".join(camera.devices()) or _("no /dev/video* devices")),
                [("zbarcam", bin_("zbarcam")), ("opencv", "opencv" in camera.providers())],
                camera.install_hint(),
            ),
            (
                _("Dialogs"),
                [("kdialog", bin_("kdialog")), ("zenity", bin_("zenity"))],
                _("install kdialog or zenity"),
            ),
            (
                _("Notifications"),
                [("org.freedesktop.Notifications", await dbus("org.freedesktop.Notifications"))],
                _("without notifications, errors only go to the journal"),
            ),
        ]
        from . import install

        print(_("Installation"))
        for key, path in install.paths().items():
            print(f"  {OK if path.exists() else NO} {key:8} {path}")
        if not install.paths()["runner"].exists():
            print(f"  {WARN} " + _("run “otprunner install” to register the runner"))
        for old in install.legacy_paths():
            if old.exists():
                print(f"  {WARN} " + _("leftover from the old version: {path} (“otprunner install” removes it)").format(path=old))

        for title, provs, hint in groups:
            print(title)
            first = next((n for n, ok in provs if ok), None)
            for n, ok in provs:
                print(f"  {OK if ok else NO} {n}" + ("  ← " + _("in use") if n == first else ""))
            if first is None:
                print(f"  {WARN} {hint}")
        return rc
    finally:
        bus.disconnect()
