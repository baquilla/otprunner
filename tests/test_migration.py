import pytest

from otprunner import migration
from otprunner.otpauth import Account, OtpError, b32encode

# Ejemplo público de exportación de Google Authenticator.
SAMPLE = (
    "otpauth-migration://offline?data=CjEKCkhlbGxvId6tvu8SGEV4YW1wbGU6YWxpY2VAZ29vZ2xlLmNvbRoHRXhhbXBsZSABKAEwAhAB"
    "GAEgACjr4JKCAg%3D%3D"
)


def test_decode_sample():
    batch = migration.decode(SAMPLE)
    (a,) = batch.accounts
    assert b32encode(a.secret) == "JBSWY3DPEHPK3PXP"
    assert (a.issuer, a.name, a.type, a.digits, a.algorithm) == ("Example", "Example:alice@google.com", "totp", 6, "SHA1")
    assert (batch.batch_size, batch.batch_index) == (1, 0)


def _accounts(n):
    return [
        Account(secret=bytes([i + 1]) * 10, name=f"user{i}@x.org", issuer=f"Svc{i}", digits=8 if i % 2 else 6,
                algorithm=["SHA1", "SHA256", "SHA512"][i % 3])
        for i in range(n)
    ]


def test_roundtrip_batches():
    accs = _accounts(23)
    uris = migration.encode(accs, batch_size=10)
    assert len(uris) == 3
    batches = [migration.decode(u) for u in uris]
    assert [b.batch_index for b in batches] == [0, 1, 2]
    assert {b.batch_size for b in batches} == {3}
    assert len({b.batch_id for b in batches}) == 1
    assert [a for b in batches for a in b.accounts] == accs


def test_hotp_roundtrip():
    a = Account(secret=b"0123456789", name="h", type="hotp", counter=2**40)
    (uri,) = migration.encode([a])
    assert migration.decode(uri).accounts == [a]


def test_plus_unescaped_in_data():
    # Algunas herramientas no escapan '+' en el query string.
    accs = _accounts(4)
    (uri,) = migration.encode(accs)
    from urllib.parse import unquote

    raw = "otpauth-migration://offline?data=" + unquote(uri.split("data=", 1)[1])
    assert migration.decode(raw).accounts == accs


def test_unsupported_period():
    with pytest.raises(OtpError):
        migration.encode([Account(secret=b"x" * 10, name="p", period=60)])


@pytest.mark.parametrize("uri", ["otpauth-migration://offline", "otpauth-migration://offline?data=CjEK", "otpauth://totp/x?secret=AA"])
def test_decode_invalid(uri):
    with pytest.raises(OtpError):
        migration.decode(uri)
