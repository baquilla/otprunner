import pytest

from otprunner.otpauth import Account, OtpError, b32encode, hotp

RFC_SHA1 = b"12345678901234567890"


def test_hotp_rfc4226():
    expected = ["755224", "287082", "359152", "969429", "338314"]
    assert [hotp(RFC_SHA1, c) for c in range(5)] == expected


@pytest.mark.parametrize(
    "alg,secret,t,code",
    [
        ("SHA1", RFC_SHA1, 59, "94287082"),
        ("SHA256", b"12345678901234567890123456789012", 59, "46119246"),
        ("SHA512", b"1234567890123456789012345678901234567890123456789012345678901234", 59, "90693936"),
        ("SHA1", RFC_SHA1, 1111111109, "07081804"),
        ("SHA256", b"12345678901234567890123456789012", 20000000000, "77737706"),
    ],
)
def test_totp_rfc6238(alg, secret, t, code):
    assert Account(secret=secret, algorithm=alg, digits=8).code(at=t) == code


def test_uri_roundtrip_defaults():
    a = Account.from_uri("otpauth://totp/ACME%20Co:john@example.com?secret=JBSWY3DPEHPK3PXP&issuer=ACME%20Co")
    assert (a.issuer, a.name, a.digits, a.period, a.algorithm) == ("ACME Co", "ACME Co:john@example.com", 6, 30, "SHA1")
    assert a.label == "ACME Co:john@example.com"
    assert Account.from_uri(a.to_uri()) == a


def test_uri_roundtrip_params():
    a = Account(secret=b"abcdefghij", name="x", issuer="", algorithm="SHA256", digits=8, period=60)
    uri = a.to_uri()
    assert "algorithm=SHA256" in uri and "digits=8" in uri and "period=60" in uri
    assert Account.from_uri(uri) == a


def test_hotp_uri():
    a = Account.from_uri("otpauth://hotp/x?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&counter=3")
    assert a.type == "hotp" and a.counter == 3 and a.code() == "969429"


def test_lowercase_and_spaced_secret():
    a = Account.from_uri("otpauth://totp/x?secret=jbsw y3dp ehpk 3pxp")
    assert b32encode(a.secret) == "JBSWY3DPEHPK3PXP"


@pytest.mark.parametrize(
    "uri",
    [
        "http://totp/x?secret=JBSWY3DP",
        "otpauth://totp/x",
        "otpauth://totp/x?secret=1",
        "otpauth://foo/x?secret=JBSWY3DP",
        "otpauth://totp/x?secret=JBSWY3DP&digits=abc",
        "otpauth://totp/x?secret=JBSWY3DP&algorithm=SHA3",
    ],
)
def test_invalid(uri):
    with pytest.raises(OtpError):
        Account.from_uri(uri)


def test_control_chars_cleaned():
    a = Account.from_uri("otpauth://totp/Github%0A:github.com%2Fyo?secret=JBSWY3DP&issuer=Github%0A")
    assert (a.issuer, a.name, a.label) == ("Github", "Github:github.com/yo", "Github:github.com/yo")


@pytest.mark.parametrize(
    "path,issuer,label",
    [
        ("alice", "", "alice"),  # sin issuer: la etiqueta tal cual
        ("GitHub:alice", "", "GitHub:alice"),  # nunca se parte por «:» ni se deduce issuer
        ("alice", "GitHub", "GitHub:alice"),  # el issuer se antepone
        ("GitHub:alice", "GitHub", "GitHub:alice"),  # …salvo que ya esté como prefijo
        ("PayPal:PayPal:yo", "PayPal", "PayPal:PayPal:yo"),  # nunca se recorta
        ("x:y", "GitHub", "GitHub:x:y"),
    ],
)
def test_label_rules(path, issuer, label):
    uri = f"otpauth://totp/{path}?secret=JBSWY3DP" + (f"&issuer={issuer}" if issuer else "")
    assert Account.from_uri(uri).label == label


def test_original_uri_kept_verbatim():
    uri = "otpauth://totp/GitHub:alice?secret=jbswy3dp&foo=bar&period=30"
    a = Account.from_uri("  " + uri + "\n")
    assert a.to_uri() == uri and "issuer" not in a.to_uri()


def test_with_counter_only_touches_counter():
    uri = "otpauth://hotp/x?secret=JBSWY3DP&counter=3&issuer=Y&foo=1"
    assert Account.from_uri(uri).with_counter(4).to_uri() == uri.replace("counter=3", "counter=4")
    assert Account.from_uri("otpauth://hotp/x?secret=JBSWY3DP").with_counter(1).to_uri().endswith("&counter=1")
