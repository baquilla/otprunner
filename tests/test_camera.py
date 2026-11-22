import asyncio

from otprunner import camera, migration
from otprunner.otpauth import Account

ACCS = [Account(secret=bytes([i]) * 10, name=f"n{i}") for i in range(1, 6)]


def test_collector_single_otpauth():
    c = camera.Collector()
    assert not c.feed("hola") and not c.feed("")
    assert c.feed(ACCS[0].to_uri()) and c.texts == [ACCS[0].to_uri()]


def test_collector_waits_for_all_batches_and_dedupes():
    msgs = []
    uris = migration.encode(ACCS, batch_size=2)  # 3 lotes
    c = camera.Collector(msgs.append)
    assert not c.feed(uris[1])
    assert not c.feed(uris[1])  # repetido (la cámara lo lee muchas veces)
    assert not c.feed(uris[0])
    assert c.feed(uris[2])
    assert len(c.texts) == 3 and len(msgs) == 2 and "Lote 2 de 3" in msgs[0]


async def test_zbarcam_parsing(monkeypatch, tmp_path):
    """Simula zbarcam con un script que imprime líneas como él."""
    uri = ACCS[0].to_uri()
    fake = tmp_path / "zbarcam"
    fake.write_text(f"#!/bin/sh\necho 'EAN-13:1234567890128'\necho 'QR-Code:{uri}'\nexec sleep 30\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(camera, "devices", lambda: ["/dev/video0"])
    monkeypatch.setattr(camera.importlib.util, "find_spec", lambda name: None)
    texts = await asyncio.wait_for(camera.scan(timeout=10), 10)
    assert texts == [uri]


async def test_no_provider(monkeypatch):
    monkeypatch.setattr(camera, "providers", lambda: [])
    try:
        await camera.scan()
    except camera.CameraError as e:
        assert "zbar" in str(e)
    else:
        raise AssertionError
