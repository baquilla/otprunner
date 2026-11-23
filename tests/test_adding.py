from otprunner import adding, capture, migration
from otprunner.otpauth import Account
from otprunner.store import MemoryStore

A = Account(secret=b"a" * 10, name="alice", issuer="GitHub")


async def test_add_uri_with_name():
    s = MemoryStore()
    out = await adding.add(s, "uri", None, name="Trabajo", uri=A.to_uri())
    assert out.ok and await s.names() == ["Trabajo"]
    assert out.summary()[0] == "Added: Trabajo"


async def test_add_clipboard_text_then_image(monkeypatch):
    calls = []

    async def text(bus):
        return "nada útil"

    async def image():
        calls.append("img")
        return [A.to_uri()]

    monkeypatch.setattr(capture, "clipboard_text", text)
    monkeypatch.setattr(capture, "clipboard_image_qr", image)
    s = MemoryStore()
    out = await adding.add(s, "clipboard", None)
    assert calls == ["img"] and out.result.added == ["GitHub:alice"]


async def test_summary_batches_and_errors():
    accs = [Account(secret=bytes([i]) * 10, name=f"n{i}") for i in range(1, 4)]
    uris = migration.encode(accs, batch_size=2)
    s = MemoryStore()
    out = await adding.add(s, "uri", None, uri=uris[0] + " otpauth://totp/x?secret=1")
    title, body = out.summary()
    assert title == "Added 2 accounts"
    assert "batch 1 of 2 — capture the next QR code" in body and "base32" in body
    out = await adding.add(s, "uri", None, uri=uris[0])
    assert out.summary()[0] == "Nothing new to add"
    out = await adding.add(s, "uri", None, uri="hola")
    assert not out.ok and out.summary()[0] == "No otpauth code found"


def test_decode_qr_roundtrip(tmp_path):
    import segno

    uri = migration.encode([A])[0]
    p = tmp_path / "qr.png"
    segno.make(uri, error="m").save(str(p), scale=4, border=4)
    assert capture.decode_qr(p) == [uri]
