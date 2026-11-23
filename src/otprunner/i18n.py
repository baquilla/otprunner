"""Traducciones con gettext. El idioma fuente es el inglés; los catálogos van en ``locale/``.

No usamos la selección por defecto de gettext: con ``LANGUAGE=en_US:es`` buscaría un
catálogo «en», no lo encontraría y caería en el español aunque el usuario prefiera inglés.
Aquí gana el primer idioma de la lista que sea inglés o que tenga catálogo.
"""

from __future__ import annotations

import gettext
import os
from importlib.resources import files

DOMAIN = "otprunner"

_tr: gettext.NullTranslations | None = None


def localedir() -> str:
    return str(files("otprunner") / "locale")


def available() -> list[str]:
    """Idiomas con catálogo compilado (además del inglés, que es el fuente)."""
    base = files("otprunner") / "locale"
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if (d / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file())


def _preferred() -> list[str]:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return [lang for lang in value.split(":") if lang]
    return []


def translation_for(language: str | None) -> gettext.NullTranslations:
    langs = [language] if language else _preferred()
    for lang in langs:
        code = lang.split(".")[0].split("@")[0]
        if code in ("C", "POSIX") or code == "en" or code.startswith("en_"):
            break
        t = gettext.translation(DOMAIN, localedir(), languages=[code], fallback=True)
        if type(t) is not gettext.NullTranslations:
            return t
    return gettext.NullTranslations()


def setup(language: str | None = None) -> None:
    """Fija el idioma (None = el del entorno). Llamar tras leer la configuración."""
    global _tr
    _tr = translation_for(language)


def _translations() -> gettext.NullTranslations:
    if _tr is None:
        setup()
    return _tr


def _(message: str) -> str:
    return _translations().gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translations().ngettext(singular, plural, n)


def N_(message: str) -> str:
    """Marca una cadena para extraerla sin traducirla aún (se traduce donde se use)."""
    return message
