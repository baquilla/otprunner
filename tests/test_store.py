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


async def test_import_name_only_for_single():
    s = MemoryStore()
    assert (await importer.import_accounts(s, [A], name="mio")).added == ["mio"]
    assert (await importer.import_accounts(s, [B, Account(secret=b"z" * 10, name="z")], name="x")).added == [
        "GitHub:bob", "z"
    ]


def test_parse_text_mixed():
    from otprunner import migration

    text = f"basura {A.to_uri()}\n{migration.encode([B])[0]} otpauth://totp/x?secret=1 fin"
    p = importer.parse_text(text)
    assert p.accounts == [A, B] and len(p.batches) == 1 and len(p.errors) == 1
