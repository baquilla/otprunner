"""Configuración opcional en ``$XDG_CONFIG_HOME/otprunner/config.toml``.

Ejemplo::

    backend = "auto"            # auto | secretservice | kwallet
    keywords = ["otp", "otpr"]  # palabras clave en KRunner
    idle_timeout = 600          # segundos sin uso antes de cerrar el servicio (0 = nunca)
    show_codes = "selected"     # selected: solo en la línea seleccionada | always | never
    max_results = 15            # resultados que caben en KRunner (bajar si comparte la lista con otros runners)
    language = "es"             # idioma de la interfaz (por defecto, el del escritorio)
    camera = "/dev/video0"      # dispositivo de la cámara (por defecto, el del lector)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from .i18n import _

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


SHOW_CODES = ("selected", "always", "never")


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "otprunner" / "config.toml"


@dataclass
class Config:
    backend: str = "auto"
    keywords: list[str] = field(default_factory=lambda: ["otp", "otpr"])
    idle_timeout: float = 600
    show_codes: str = "selected"
    max_results: int = 15
    camera: str | None = None
    language: str | None = None


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return cfg
    except (OSError, tomllib.TOMLDecodeError) as e:
        print("otprunner: " + _("ignoring {path}: {error}").format(path=path, error=e), file=sys.stderr)
        return cfg
    if isinstance(data.get("backend"), str):
        cfg.backend = data["backend"]
    kw = data.get("keywords")
    if isinstance(kw, list) and kw and all(isinstance(k, str) and k for k in kw):
        cfg.keywords = kw
    idle = data.get("idle_timeout")
    if isinstance(idle, (int, float)) and not isinstance(idle, bool) and idle >= 0:
        cfg.idle_timeout = idle
    show = data.get("show_codes")
    if show in SHOW_CODES:
        cfg.show_codes = show
    elif show is not None:
        print("otprunner: " + _("invalid show_codes={value} (use {valid})").format(
            value=repr(show), valid=", ".join(SHOW_CODES)), file=sys.stderr)
    limit = data.get("max_results")
    if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 3:
        cfg.max_results = limit
    if isinstance(data.get("camera"), str) and data["camera"]:
        cfg.camera = data["camera"]
    if isinstance(data.get("language"), str) and data["language"]:
        cfg.language = data["language"]
    return cfg
