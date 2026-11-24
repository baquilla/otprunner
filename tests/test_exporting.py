from otprunner import exporting, migration
from otprunner.otpauth import Account


def test_build_skips_incompatible():
    accs = {
        "a": Account(secret=b"a" * 10, name="a"),
        "p60": Account(secret=b"b" * 10, name="p", period=60),
        "d7": Account(secret=b"c" * 10, name="d", digits=7),
    }
    exp = exporting.build(accs)
    assert exp.exported == ["a"] and [n for n, _ in exp.skipped] == ["p60", "d7"]
    assert migration.decode(exp.uris[0]).accounts == [accs["a"]]


def test_single_account_exports_its_otpauth_uri():
    uri = "otpauth://totp/x?secret=JBSWY3DP&period=60&foo=1"
    exp = exporting.build({"x": Account.from_uri(uri)})
    assert exp.uris == [uri] and exp.exported == ["x"] and not exp.skipped
    assert exporting.build({"x": Account.from_uri(uri)}, single_otpauth=False).skipped


def test_write_sheet_has_all_codes(tmp_path):
    accs = [Account(secret=bytes([i + 1]) * 10, name=f"u{i}", issuer="S") for i in range(13)]
    uris = migration.encode(accs, batch_size=5)
    path = exporting.write_sheet(uris, ["1/3", "2/3", "3/3"], tmp_path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    import zxingcpp
    from PIL import Image

    found = sorted(r.text for r in zxingcpp.read_barcodes(Image.open(path)))
    assert found == sorted(uris)


LISTING = """Monitors: 3
 0: +*eDP1 1920/310x1080/170+319+1080  eDP1
 1: +DP1 1920/310x515/80+319+2160  DP1
 2: +HDMI1 2560/670x1080/280+0+0  HDMI1
"""


def test_image_area_follows_pointer_or_smallest_monitor():
    from otprunner import dialogs

    mons = dialogs.monitors(LISTING)
    assert mons[1] == (1920, 515, 319, 2160)
    assert dialogs.pointer("X=500\nY=2300\nSCREEN=0\nWINDOW=1\n") == (500, 2300)
    assert dialogs.image_area(mons=mons, ptr=(500, 2300)) == (1280, 355)  # el monitor bajo
    assert dialogs.image_area(mons=mons, ptr=(100, 100)) == (1280, 760)  # el grande
    assert dialogs.image_area(mons=mons, ptr=(-5000, 0)) == (1280, 355)  # desconocido: el menor
    assert dialogs.image_area(mons=[]) == (1280, 760)


def test_sheet_fits_a_short_monitor(tmp_path):
    from PIL import Image

    accs = [Account(secret=bytes([i + 1]) * 20, name=f"user{i}@example.com", issuer=f"Svc{i}") for i in range(16)]
    uris = migration.encode(accs)
    path = exporting.write_sheet(uris, ["1/2", "2/2"], tmp_path, max_width=1280, max_height=355)
    assert Image.open(path).height <= 355
    import zxingcpp

    assert sorted(r.text for r in zxingcpp.read_barcodes(Image.open(path))) == sorted(uris)
