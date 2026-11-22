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
