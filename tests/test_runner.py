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
    assert props["subtext"].startswith("valid until ") and "next: " in props["subtext"]
    ms = await r.match("otp a")
    assert {m[0].split(runner.SEP)[1] for m in ms if m[0].startswith("code")} == {"GitHub:alice", "PayPal:bob"}
    assert ms[-1][0] == f"query{runner.SEP}otp add "  # comando sugerido al final
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
    assert (await r.match("otp pay"))[0][0] == "none"


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
    assert [m[0] for m in ms] == [f"add{runner.SEP}{src}{runner.SEP}Mi Banco" for src in ("screen", "clipboard", "camera")]
    assert "“Mi Banco”" in ms[0][1]
    assert len(await r.match("otp add")) == 3


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
    names = [m[0].split(runner.SEP)[1] for m in await r.match("otp X:") if m[0].startswith("code")]
    assert names == ["X:n1", "X:n2"]  # la caché se invalidó


async def test_run_add_cancelled_is_silent(store, monkeypatch):
    from otprunner import capture

    async def cancelled(bus, delay=0.4):
        raise capture.CaptureCancelled("cancelada")

    monkeypatch.setattr(capture, "from_screen", cancelled)
    await make(store).run(f"add{runner.SEP}screen{runner.SEP}x", "")
    assert len(store.data) == 3


async def test_manage_matches(store):
    r = make(store)
    ms = await r.match("otp rm git")
    assert [m[0] for m in ms] == [f"remove{runner.SEP}GitHub:alice"] and "Remove" in ms[0][1]
    assert [m[0] for m in await r.match("otp remove git")] == [f"remove{runner.SEP}GitHub:alice"]
    ms = await r.match("otp rename")
    assert len(ms) == 3 and all(m[0].startswith("rename") for m in ms)
    (m,) = await r.match("otp export pay")
    assert m[0] == f"export{runner.SEP}pay" and "1 account " in m[1]
    assert (await r.match("otp rm zzz"))[0][0] == "none"


async def test_run_rm_rename_with_dialogs(store, monkeypatch):
    from otprunner import dialogs

    answers = {"confirm": False, "text": "Nuevo"}

    async def confirm(*a, **k):
        return answers["confirm"]

    async def ask_text(*a, **k):
        return answers["text"]

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(dialogs, "ask_text", ask_text)
    r = make(store)
    await r.run(f"remove{runner.SEP}hotp", "")
    assert "hotp" in store.data  # cancelado
    answers["confirm"] = True
    await r.run(f"remove{runner.SEP}hotp", "")
    assert "hotp" not in store.data
    await r.run(f"rename{runner.SEP}PayPal:bob", "")
    assert "Nuevo" in store.data and "PayPal:bob" not in store.data


async def test_run_export_shows_and_deletes(store, monkeypatch, tmp_path):
    from otprunner import capture, dialogs

    shown = []

    async def confirm(*a, **k):
        return True

    async def show(path, title):
        assert path.exists() and oct(path.stat().st_mode)[-3:] == "600"
        shown.append(capture.decode_qr(path)[0])

    monkeypatch.setattr(dialogs, "confirm", confirm)
    monkeypatch.setattr(dialogs, "show_image", show)
    monkeypatch.setattr(capture, "private_dir", lambda: tmp_path)
    await make(store).run(f"export{runner.SEP}", "")
    from otprunner import migration

    assert len(shown) == 1 and len(migration.decode(shown[0]).accounts) == 3
    assert list(tmp_path.iterdir()) == []


def _ids(ms):
    return [m[0] for m in ms]


async def test_empty_query_shows_commands_only(store):
    ms = await make(store).match("otp")
    assert not any(i.startswith("code") for i in _ids(ms))
    assert "3 accounts" in ms[0][1]
    assert _ids(ms)[1:] == [f"query{runner.SEP}otp {c} " for c in ("add", "rename", "remove", "export")]


async def test_prefix_suggests_commands_after_accounts(store):
    ms = await make(store).match("otp re")
    assert _ids(ms) == ["none", f"query{runner.SEP}otp rename ", f"query{runner.SEP}otp remove "]  # ninguna con «re»
    ms = await make(store).match("otp h")
    assert _ids(ms)[0] == f"code{runner.SEP}GitHub:alice" and _ids(ms)[-1] != f"query{runner.SEP}otp add "


async def test_result_limit_keeps_commands_visible():
    s = MemoryStore()
    for i in range(30):
        await s.put(f"acc{i:02d}a", Account(secret=bytes([i + 1]) * 10, name=f"a{i}"))
    r = make(s)
    r.cfg.max_results = 15
    ms = await r.match("otp a")
    assert len(ms) == 15
    assert ms[-1][0] == f"query{runner.SEP}otp add "
    assert "+17 more" in ms[-2][1] and ms[-2][0] == f"query{runner.SEP}otp a"
    ms = await r.match("otp remove")
    assert len(ms) == 15 and "+16 more" in ms[-1][1]


async def test_max_results_configurable():
    s = MemoryStore()
    for i in range(30):
        await s.put(f"acc{i:02d}a", Account(secret=bytes([i + 1]) * 10, name=f"a{i}"))
    r = make(s)
    assert r.cfg.max_results == 7  # por defecto
    ms = await r.match("otp a")
    assert len(ms) == 7 and ms[-1][0] == f"query{runner.SEP}otp add " and "+25 more" in ms[-2][1]
