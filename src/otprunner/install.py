"""Registro del runner en el escritorio del usuario (sin root).

Ficheros que se crean:

- ``$XDG_DATA_HOME/krunner/dbusplugins/otprunner.desktop``: metadatos del runner
  (Plasma 5.27 y 6 leen este directorio).
- ``$XDG_DATA_HOME/dbus-1/services/<bus>.service``: activación por DBus.
- ``$XDG_CONFIG_HOME/systemd/user/otprunner.service``: si hay systemd de usuario;
  la activación DBus delega en él (logs en journalctl, reinicio en fallos).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import APP_NAME, __version__, config, i18n
from .i18n import N_, _
from .runner import BUS_NAME, OBJECT_PATH

UNIT = "otprunner.service"
# Sin traducir aquí: el .desktop lleva Comment[xx] para cada catálogo disponible.
COMMENT = N_("TOTP codes from the system keystore")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


ICON = "otprunner"
# (fichero del paquete, directorio del tema hicolor): versión simplificada en 16/22 px
ICON_FILES = (
    ("otprunner.svg", "scalable/apps"),
    ("otprunner-small.svg", "16x16/apps"),
    ("otprunner-small.svg", "22x22/apps"),
)


def paths() -> dict[str, Path]:
    icons = _data_home() / "icons/hicolor"
    return {
        "runner": _data_home() / "krunner/dbusplugins/otprunner.desktop",
        "dbus": _data_home() / f"dbus-1/services/{BUS_NAME}.service",
        "systemd": _config_home() / "systemd/user" / UNIT,
        **{f"icon {d.split('/')[0]}": icons / d / f"{ICON}.svg" for _, d in ICON_FILES},
    }


def install_icons() -> list[Path]:
    from importlib.resources import files

    out = []
    icons = _data_home() / "icons/hicolor"
    for src, d in ICON_FILES:
        dest = icons / d / f"{ICON}.svg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((files("otprunner") / "data" / src).read_bytes())
        out.append(dest)
    # Si el usuario tiene caché de iconos en hicolor, que se regenere.
    if (icons / "icon-theme.cache").exists():
        _run(["gtk-update-icon-cache", "-f", "-t", str(icons)])
    else:
        os.utime(icons)
    return out


def legacy_paths() -> list[Path]:
    """Restos de la versión antigua (kservices5 + org.kde.otprunner)."""
    return [
        _data_home() / "kservices5/otprunner.desktop",
        _data_home() / "dbus-1/services/otprunner.service",
    ]


def exec_line() -> str:
    exe = sys.executable
    if any(c.isspace() for c in exe):
        raise RuntimeError(_("the interpreter path contains spaces, which is not supported: {path}").format(path=exe))
    return f"{exe} -m otprunner serve"


def has_systemd_user() -> bool:
    if not shutil.which("systemctl"):
        return False
    r = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True)
    return r.returncode == 0


def match_regex(keywords: list[str]) -> str | None:
    """Regex que KRunner aplica antes de llamarnos (evita una llamada DBus por tecla)."""
    if not keywords or not all(re.fullmatch(r"[\w-]+", k) for k in keywords):
        return None
    return "(?i)^(" + "|".join(keywords) + ")( .*)?$"


def runner_desktop(cfg: config.Config) -> str:
    lines = [
        "[Desktop Entry]",
        f"Name={APP_NAME}",
        f"Comment={COMMENT}",
        *(f"Comment[{lang}]={i18n.translation_for(lang).gettext(COMMENT)}" for lang in i18n.available()),
        f"Icon={ICON}",
        "Type=Service",
        "X-KDE-ServiceTypes=Plasma/Runner",
        "X-KDE-PluginInfo-Name=otprunner",
        f"X-KDE-PluginInfo-Version={__version__}",
        "X-KDE-PluginInfo-License=GPL-3.0-or-later",
        "X-KDE-PluginInfo-EnabledByDefault=true",
        "X-Plasma-API=DBus",
        "X-Plasma-API-Minimum-Version=2.0",
        f"X-Plasma-DBusRunner-Service={BUS_NAME}",
        f"X-Plasma-DBusRunner-Path={OBJECT_PATH}",
        "X-Plasma-Request-Actions-Once=true",
    ]
    rx = match_regex(cfg.keywords)
    if rx:
        lines.append(f"X-Plasma-Runner-Match-Regex={rx}")
    return "\n".join(lines) + "\n"


def dbus_service(systemd: bool) -> str:
    out = f"[D-BUS Service]\nName={BUS_NAME}\nExec={exec_line()}\n"
    if systemd:
        out += f"SystemdService={UNIT}\n"
    return out


def systemd_unit() -> str:
    return f"""[Unit]
Description={APP_NAME}: códigos TOTP para KRunner
PartOf=graphical-session.target

[Service]
Type=dbus
BusName={BUS_NAME}
ExecStart={exec_line()}
Restart=on-failure
RestartSec=2
"""


def _run(cmd: list[str]) -> None:
    if shutil.which(cmd[0]):
        subprocess.run(cmd, capture_output=True)


def restart_krunner() -> None:
    # KRunner se relanza solo por activación DBus la próxima vez que se abre.
    for q in ("kquitapp6", "kquitapp5"):
        if shutil.which(q):
            _run([q, "krunner"])
            return


def install(verbose: bool = True) -> int:
    cfg = config.load()
    systemd = has_systemd_user()
    p = paths()
    files = {"runner": runner_desktop(cfg), "dbus": dbus_service(systemd)}
    if systemd:
        files["systemd"] = systemd_unit()
    for key, content in files.items():
        p[key].parent.mkdir(parents=True, exist_ok=True)
        p[key].write_text(content)
        if verbose:
            print(_("written: {path}").format(path=p[key]))
    for icon in install_icons():
        if verbose:
            print(_("written: {path}").format(path=icon))
    for old in legacy_paths():
        if old.exists() and "otprunner" in old.read_text(errors="replace"):
            old.unlink()
            if verbose:
                print(_("removed (old version): {path}").format(path=old))
    if systemd:
        _run(["systemctl", "--user", "daemon-reload"])
        # Si había una instancia corriendo, que coja el código/config nuevos.
        _run(["systemctl", "--user", "try-restart", UNIT])
    restart_krunner()
    if verbose:
        kws = " / ".join(cfg.keywords)
        print("\n" + _("Done. Open KRunner and type “{keywords}”.").format(keywords=kws))
        if systemd:
            print(_("Logs: {command}").format(command=f"journalctl --user -u {UNIT}"))
    return 0


def uninstall(verbose: bool = True) -> int:
    if has_systemd_user():
        _run(["systemctl", "--user", "stop", UNIT])
    for f in [*paths().values(), *legacy_paths()]:
        if f.exists():
            f.unlink()
            if verbose:
                print(_("removed: {path}").format(path=f))
    if has_systemd_user():
        _run(["systemctl", "--user", "daemon-reload"])
    restart_krunner()
    if verbose:
        print(_("Uninstalled. The secrets are still in the keystore."))
    return 0
