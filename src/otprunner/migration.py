"""Códec ``otpauth-migration://`` (exportación de Google Authenticator).

La URI lleva en ``data`` un protobuf ``MigrationPayload`` en base64::

    MigrationPayload { repeated OtpParameters otp_parameters = 1; int32 version = 2;
                       int32 batch_size = 3; int32 batch_index = 4; int32 batch_id = 5; }
    OtpParameters    { bytes secret = 1; string name = 2; string issuer = 3;
                       Algorithm algorithm = 4; DigitCount digits = 5; OtpType type = 6;
                       int64 counter = 7; }

Implementado a mano (solo varint y length-delimited) para no depender de ``protobuf``.
El formato no admite periodo distinto de 30 s ni dígitos distintos de 6/8.
"""

from __future__ import annotations

import base64
import random
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, urlsplit

from .otpauth import Account, OtpError

SCHEME = "otpauth-migration"
# Google Authenticator no lee bien QR más densos.
DEFAULT_BATCH = 10

_ALG = {0: "SHA1", 1: "SHA1", 2: "SHA256", 3: "SHA512", 4: "MD5"}
_ALG_R = {"SHA1": 1, "SHA256": 2, "SHA512": 3, "MD5": 4}
_DIG = {0: 6, 1: 6, 2: 8}
_DIG_R = {6: 1, 8: 2}
_TYP = {0: "totp", 1: "hotp", 2: "totp"}
_TYP_R = {"hotp": 1, "totp": 2}


@dataclass(frozen=True)
class Batch:
    accounts: list[Account]
    batch_size: int = 1
    batch_index: int = 0
    batch_id: int = 0


# --- protobuf mínimo ----------------------------------------------------------
def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        if i >= len(b):
            raise OtpError("protobuf truncado")
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _fields(b: bytes):
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            n, i = _varint(b, i)
            if i + n > len(b):
                raise OtpError("protobuf truncado")
            v, i = b[i : i + n], i + n
        elif wt == 1:
            v, i = b[i : i + 8], i + 8
        elif wt == 5:
            v, i = b[i : i + 4], i + 4
        else:
            raise OtpError(f"protobuf: wire type {wt} no soportado")
        yield num, v


def _enc_varint(n: int) -> bytes:
    n &= (1 << 64) - 1  # int64 negativos como en protobuf
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _f_varint(num: int, v: int) -> bytes:
    return _enc_varint(num << 3) + _enc_varint(v)


def _f_bytes(num: int, v: bytes) -> bytes:
    return _enc_varint(num << 3 | 2) + _enc_varint(len(v)) + v


# --- API ----------------------------------------------------------------------
def is_migration_uri(text: str) -> bool:
    return text.strip().lower().startswith(SCHEME + "://")


def decode(uri: str) -> Batch:
    parts = urlsplit(uri.strip())
    if parts.scheme.lower() != SCHEME:
        raise OtpError("no es una URI otpauth-migration://")
    data = parse_qs(parts.query).get("data")
    if not data:
        raise OtpError("falta el parámetro data")
    # parse_qs convierte '+' sin escapar en espacio
    raw = data[0].replace(" ", "+")
    try:
        payload = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"+/", validate=False)
    except ValueError as e:
        raise OtpError(f"data no es base64 válido: {e}") from None

    accounts: list[Account] = []
    meta = {3: 1, 4: 0, 5: 0}
    for num, v in _fields(payload):
        if num == 1:
            accounts.append(_decode_params(v))
        elif num in meta and isinstance(v, int):
            meta[num] = v
    return Batch(accounts, batch_size=meta[3] or 1, batch_index=meta[4], batch_id=meta[5])


def _decode_params(b: bytes) -> Account:
    o: dict[int, object] = {}
    for num, v in _fields(b):
        o[num] = v

    def text(n: int) -> str:
        v = o.get(n, b"")
        return v.decode("utf-8") if isinstance(v, bytes) else ""

    name, issuer = text(2), text(3)
    if issuer and name.startswith(issuer + ":"):
        name = name[len(issuer) + 1 :]
    return Account(
        secret=o.get(1, b""),  # type: ignore[arg-type]
        name=name,
        issuer=issuer,
        type=_TYP.get(o.get(6, 2), "totp"),  # type: ignore[arg-type]
        algorithm=_ALG.get(o.get(4, 1), "SHA1"),  # type: ignore[arg-type]
        digits=_DIG.get(o.get(5, 1), 6),  # type: ignore[arg-type]
        counter=o.get(7, 0),  # type: ignore[arg-type]
    )


def _encode_params(a: Account) -> bytes:
    if a.digits not in _DIG_R:
        raise OtpError(f"{a.label}: otpauth-migration solo admite 6 u 8 dígitos")
    if a.type == "totp" and a.period != 30:
        raise OtpError(f"{a.label}: otpauth-migration solo admite periodo de 30 s")
    out = _f_bytes(1, a.secret) + _f_bytes(2, a.name.encode()) + _f_bytes(3, a.issuer.encode())
    out += _f_varint(4, _ALG_R[a.algorithm]) + _f_varint(5, _DIG_R[a.digits]) + _f_varint(6, _TYP_R[a.type])
    if a.type == "hotp":
        out += _f_varint(7, a.counter)
    return out


def encode(accounts: list[Account], batch_size: int = DEFAULT_BATCH) -> list[str]:
    """Codifica las cuentas en una o varias URIs (lotes de ``batch_size``)."""
    if not accounts:
        return []
    chunks = [accounts[i : i + batch_size] for i in range(0, len(accounts), batch_size)]
    batch_id = random.randint(1, 2**31 - 1)
    uris = []
    for idx, chunk in enumerate(chunks):
        payload = b"".join(_f_bytes(1, _encode_params(a)) for a in chunk)
        payload += _f_varint(2, 1) + _f_varint(3, len(chunks)) + _f_varint(4, idx) + _f_varint(5, batch_id)
        data = base64.b64encode(payload).decode()
        uris.append(f"{SCHEME}://offline?data={quote(data, safe='')}")
    return uris
