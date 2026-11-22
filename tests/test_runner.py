import pytest

from otprunner import clipboard, config, runner
from otprunner.otpauth import Account
from otprunner.store import MemoryStore, StoreUnavailable

GH = Account(secret=b"12345678901234567890", name="alice", issuer="GitHub")
PP = Account(secret=b"abcdefghijabcdefghij", name="bob", issuer="PayPal")
HO = Account(secret=b"12345678901234567890", name="h", type="hotp", counter=0)


@pytest.fixture
def store():
    s = MemoryStore()
    s.data = {"GitHub:alice": GH.to_uri(), "PayPal:bob": PP.to_uri(), "hotp": HO.to_uri()}
    return s


def make(store, show_codes="always", **kw):
    async def factory():
        return store

    return runner.Runner(config.Config(show_codes=show_codes), factory, **kw)


@pytest.mark.parametrize("q,expected", [("otp", ""), ("OTP  pay ", "pay"), ("otpr git", "git"), ("otpx", None),
                                        ("hola otp", None), ("", None)])
def test_parse(store, q, expected):
    assert make(store).parse(q) == expected


async def test_match_filters_and_formats(store):
    r = make(store)
    assert await r.match("firefox") == []
    ms = await r.match("otp pay")
    assert [m[0] for m in ms] == [f"code{runner.SEP}PayPal:bob"]
    mid, text, icon, typ, rel, props = ms[0]
    code, name = text.split("   ")
    assert len(code) == 7 and name == "PayPal:bob" and typ == runner.EXACT
    assert props["subtext"].startswith("vale hasta las ") and "después: " in props["subtext"]
    ms = await r.match("otp")
    assert {m[0].split(runner.SEP)[1] for m in ms if m[0].startswith("code")} == {"GitHub:alice", "PayPal:bob", "hotp"}
    assert ms[-1][0] == f"query{runner.SEP}otp add "  # entrada de ayuda al final
    assert (await r.match("otp zzz"))[0][0] == "none"


async def test_match_reports_store_errors():
    async def broken():
        raise StoreUnavailable("no hay keystore")

    r = runner.Runner(config.Config(), broken)
    (m,) = await r.match("otp")
    assert m[0] == "error" and "no hay keystore" in m[1] and m[3] == runner.INFORMATIONAL


async def test_cache_and_forget(store):
    r = make(store)
    await r.match("otp")
    store.data.clear()
    assert len(await r.match("otp pay")) == 1  # cacheado
    r.forget()
    assert (await r.match("otp"))[0][0] == "none"


async def test_run_copies_and_advances_hotp(store, monkeypatch):
    copied = []

    async def fake_copy(text, bus=None):
        copied.append(text)
        return "fake"

    monkeypatch.setattr(clipboard, "copy", fake_copy)
    r = make(store)
    await r.run(f"code{runner.SEP}hotp", "")
    await r.run(f"code{runner.SEP}hotp", "")
    assert copied == ["755224", "287082"]
    assert (await store.get("hotp")).counter == 2
    await r.run(f"code{runner.SEP}noexiste", "")  # no debe lanzar
    assert len(copied) == 2


def test_fmt_code():
    assert runner.fmt_code("123456") == "123 456"
    assert runner.fmt_code("12345678") == "1234 5678"


async def test_show_codes_modes(store):
    (m,) = await make(store, "selected").match("otp pay")
    assert m[1] == "PayPal:bob" and m[5]["subtext"].replace(" ", "").isdigit()
    (m,) = await make(store, "never").match("otp pay")
    assert m[1] == "PayPal:bob" and not any(c.isdigit() for c in m[5]["subtext"])


def test_config_show_codes(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('show_codes = "always"')
    assert config.load(p).show_codes == "always"
    p.write_text('show_codes = "nope"')
    assert config.load(p).show_codes == "selected"


async def test_add_matches(store):
    r = make(store)
    ms = await r.match("otp add Mi Banco")
    assert [m[0] for m in ms] == [f"add{runner.SEP}screen{runner.SEP}Mi Banco", f"add{runner.SEP}clipboard{runner.SEP}Mi Banco"]
    assert "«Mi Banco»" in ms[0][1]
    assert len(await r.match("otp add")) == 2


async def test_run_add_from_screen(store, monkeypatch):
    from otprunner import capture, migration

    new = [Account(secret=bytes([i]) * 10, name=f"n{i}", issuer="X") for i in range(1, 4)]
    uris = migration.encode(new, batch_size=2)

    async def fake_screen(bus, delay=0.4):
        return [uris[0]]

    monkeypatch.setattr(capture, "from_screen", fake_screen)
    r = make(store)
    await r.match("otp")  # llena la caché
    await r.run(f"add{runner.SEP}screen{runner.SEP}", "")
    names = [m[0].split(runner.SEP)[1] for m in await r.match("otp X:")]
    assert names == ["X:n1", "X:n2"]  # la caché se invalidó


async def test_run_add_cancelled_is_silent(store, monkeypatch):
    from otprunner import capture

    async def cancelled(bus, delay=0.4):
        raise capture.CaptureCancelled("cancelada")

    monkeypatch.setattr(capture, "from_screen", cancelled)
    await make(store).run(f"add{runner.SEP}screen{runner.SEP}x", "")
    assert len(store.data) == 3
