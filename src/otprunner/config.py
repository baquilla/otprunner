"""Configuración opcional en ``$XDG_CONFIG_HOME/otprunner/config.toml``.

Ejemplo::

    backend = "auto"            # auto | secretservice | kwallet
    keywords = ["otp", "otpr"]  # palabras clave en KRunner
    idle_timeout = 600          # segundos sin uso antes de cerrar el servicio (0 = nunca)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "otprunner" / "config.toml"


@dataclass
class Config:
    backend: str = "auto"
    keywords: list[str] = field(default_factory=lambda: ["otp", "otpr"])
    idle_timeout: float = 600


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return cfg
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"otprunner: ignorando {path}: {e}", file=sys.stderr)
        return cfg
    if isinstance(data.get("backend"), str):
        cfg.backend = data["backend"]
    kw = data.get("keywords")
    if isinstance(kw, list) and kw and all(isinstance(k, str) and k for k in kw):
        cfg.keywords = kw
    idle = data.get("idle_timeout")
    if isinstance(idle, (int, float)) and not isinstance(idle, bool) and idle >= 0:
        cfg.idle_timeout = idle
    return cfg
