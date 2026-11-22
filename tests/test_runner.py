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


def make(store, **kw):
    async def factory():
        return store

    return runner.Runner(config.Config(), factory, **kw)


@pytest.mark.parametrize("q,expected", [("otp", ""), ("OTP  pay ", "pay"), ("otpr git", "git"), ("otpx", None),
                                        ("hola otp", None), ("", None)])
def test_parse(store, q, expected):
    assert make(store).parse(q) == expected


async def test_match_filters_and_formats(store):
    r = make(store)
    assert await r.match("firefox") == []
    ms = await r.match("otp pay")
    assert [m[1] for m in ms] == ["PayPal:bob"]
    mid, text, icon, typ, rel, props = ms[0]
    code, secs = props["subtext"].split("  ·  ")
    assert len(code) == 7 and secs.endswith(" s") and typ == runner.EXACT
    assert {m[1] for m in await r.match("otp")} == {"GitHub:alice", "PayPal:bob", "hotp"}
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
    assert len(await r.match("otp")) == 3  # cacheado
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
