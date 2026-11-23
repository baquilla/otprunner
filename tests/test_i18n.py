"""Selección de idioma y completitud de los catálogos."""

import gettext
import re
from pathlib import Path

import pytest

from otprunner import config, i18n, install, runner
from otprunner.otpauth import Account
from otprunner.store import MemoryStore

SRC = Path(__file__).parents[1] / "src" / "otprunner"
LANGS = i18n.available()


def _env(monkeypatch, **env):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


@pytest.mark.parametrize("env,expected", [
    ({"LANGUAGE": "en_US:es", "LANG": "en_US.UTF-8"}, "Delete"),   # inglés preferido, aunque haya «es» después
    ({"LANGUAGE": "es_ES:en", "LANG": "en_US.UTF-8"}, "Borrar"),
    ({"LANG": "es_ES.UTF-8"}, "Borrar"),
    ({"LANGUAGE": "fr:es"}, "Borrar"),                            # sin catálogo fr: siguiente de la lista
    ({"LANG": "C"}, "Delete"),
    ({}, "Delete"),
])
def test_language_selection(monkeypatch, env, expected):
    _env(monkeypatch, **env)
    i18n.setup()
    assert i18n._("Delete") == expected


def test_config_language_overrides_env(monkeypatch, tmp_path):
    _env(monkeypatch, LANGUAGE="en_US")
    p = tmp_path / "c.toml"
    p.write_text('language = "es"')
    i18n.setup(config.load(p).language)
    assert i18n._("Delete") == "Borrar"
    assert i18n.ngettext("{n} secret", "{n} secrets", 2).format(n=2) == "2 secretos"


def _source_messages() -> set:
    from babel.messages.extract import extract_from_dir

    keywords = {"_": None, "N_": None, "ngettext": (1, 2)}
    return {m[2] for m in extract_from_dir(str(SRC), keywords=keywords, method_map=[("**.py", "python")])}


@pytest.mark.parametrize("lang", LANGS)
def test_catalog_complete_and_compiled(lang):
    from babel.messages.pofile import read_po

    po = read_po(open(SRC / "locale" / lang / "LC_MESSAGES" / "otprunner.po", "rb"))
    by_id = {m.id: m for m in po if m.id}
    missing = [m for m in _source_messages() if m not in by_id or not by_id[m].string
               or (isinstance(by_id[m].string, tuple) and not all(by_id[m].string))]
    assert not missing, f"sin traducir en {lang} (scripts/i18n.sh update): {missing}"
    mo = gettext.translation(i18n.DOMAIN, i18n.localedir(), languages=[lang])
    ph = re.compile(r"\{\w+\}")
    for mid, m in by_id.items():
        if isinstance(mid, tuple):
            assert mo.ngettext(mid[0], mid[1], 5) == m.string[1], f".mo desactualizado (scripts/i18n.sh compile): {mid}"
            continue
        assert mo.gettext(mid) == m.string, f".mo desactualizado (scripts/i18n.sh compile): {mid!r}"
        assert set(ph.findall(mid)) == set(ph.findall(m.string)), f"marcadores distintos: {mid!r}"


async def test_runner_in_spanish():
    i18n.setup("es")
    s = MemoryStore()
    await s.put("GitHub:yo", Account(secret=b"a" * 10, name="yo", issuer="GitHub"))

    async def factory():
        return s

    r = runner.Runner(config.Config(), factory)
    assert [m[1] for m in await r.match("otp rm git")] == ["Borrar «GitHub:yo»"]
    assert (await r.match("otp export"))[0][1] == "Exportar 1 cuenta como QR para Google Authenticator"
    assert (await r.match("otp zzz"))[0][1] == "Ninguna cuenta coincide con «zzz»"


def test_desktop_comment_translated():
    desktop = install.runner_desktop(config.Config())
    assert "Comment=TOTP codes from the system keystore" in desktop
    for lang in LANGS:
        assert f"Comment[{lang}]=" in desktop
