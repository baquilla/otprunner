import pytest

from otprunner import importer
from otprunner.otpauth import Account
from otprunner.store import MemoryStore, StoreError

A = Account(secret=b"a" * 10, name="alice", issuer="GitHub")
B = Account(secret=b"b" * 10, name="bob", issuer="GitHub")


async def test_put_get_rename_delete():
    s = MemoryStore()
    await s.put("gh", A)
    assert await s.get("gh") == A
    with pytest.raises(StoreError):
        await s.put("gh", B)
    await s.rename("gh", "github")
    assert await s.names() == ["github"]
    assert await s.delete("github") and not await s.delete("github")


async def test_corrupt_entries_are_skipped():
    s = MemoryStore()
    s.data["roto"] = "basura"
    await s.put("ok", A)
    assert list(await s.all()) == ["ok"]


async def test_import_dedupe_and_suffix():
    s = MemoryStore()
    await s.put("GitHub:alice", A)
    other = Account(secret=b"c" * 10, name="alice", issuer="GitHub")
    res = await importer.import_accounts(s, [A, B, other])
    assert res.skipped == ["GitHub:alice"]
    assert res.added == ["GitHub:bob", "GitHub:alice (2)"]
    assert res.renamed == [("GitHub:alice", "GitHub:alice (2)")]


async def test_import_same_secret_updates_uri_keeps_name():
    s = MemoryStore()
    old = "otpauth://totp/GitHub:alice?secret=MFQWCYLBMFQWCYLB&issuer=GitHub"
    await importer.import_accounts(s, [Account.from_uri(old)], name="mi github")
    new = "otpauth://totp/Otro:nombre?secret=MFQWCYLBMFQWCYLB&digits=6&image=x"
    res = await importer.import_accounts(s, [Account.from_uri(new)], name="ignorado")
    assert res.updated == ["mi github"] and not res.added
    assert s.data == {"mi github": new}  # URI exacta, nombre intacto
    res = await importer.import_accounts(s, [Account.from_uri(new)])
    assert res.skipped == ["mi github"] and not res.updated


async def test_import_stores_uri_verbatim():
    s = MemoryStore()
    uri = "otpauth://totp/alice?secret=MFQWCYLBMFQWCYLB&issuer=GitHub&foo=bar"
    assert (await importer.import_accounts(s, [Account.from_uri(uri)])).added == ["GitHub:alice"]
    assert s.data["GitHub:alice"] == uri


async def test_import_name_only_for_single():
    s = MemoryStore()
    assert (await importer.import_accounts(s, [A], name="mio")).added == ["mio"]
    assert (await importer.import_accounts(s, [B, Account(secret=b"z" * 10, name="z")], name="x")).added == [
        "GitHub:bob",
        "z",
    ]


def test_parse_text_mixed():
    from otprunner import migration

    text = f"basura {A.to_uri()}\n{migration.encode([B])[0]} otpauth://totp/x?secret=1 fin"
    p = importer.parse_text(text)
    assert p.accounts == [A, B] and len(p.batches) == 1 and len(p.errors) == 1


async def test_no_session_bus_is_a_clear_error(monkeypatch):
    from otprunner import dbusutil
    from otprunner.store import open_store

    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(dbusutil.NoSessionBus, match="session bus"):
        await open_store()
