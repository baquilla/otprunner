"""Modelo de cuenta OTP y formato ``otpauth://`` (Key URI Format de Google Authenticator)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass, replace
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512, "MD5": hashlib.md5}


class OtpError(ValueError):
    """URI o parámetros OTP no válidos."""


def b32decode(secret: str) -> bytes:
    s = secret.replace(" ", "").replace("-", "").upper().rstrip("=")
    try:
        return base64.b32decode(s + "=" * (-len(s) % 8))
    except (ValueError, base64.binascii.Error) as e:
        raise OtpError(f"secreto base32 no válido: {e}") from None


def b32encode(secret: bytes) -> str:
    return base64.b32encode(secret).decode().rstrip("=")


@dataclass(frozen=True)
class Account:
    secret: bytes
    name: str = ""
    issuer: str = ""
    type: str = "totp"  # totp | hotp
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30
    counter: int = 0

    def __post_init__(self) -> None:
        if not self.secret:
            raise OtpError("secreto vacío")
        if self.type not in ("totp", "hotp"):
            raise OtpError(f"tipo no soportado: {self.type}")
        if self.algorithm not in ALGORITHMS:
            raise OtpError(f"algoritmo no soportado: {self.algorithm}")
        if not 6 <= self.digits <= 10:
            raise OtpError(f"dígitos no válidos: {self.digits}")
        if self.period <= 0:
            raise OtpError(f"periodo no válido: {self.period}")

    # --- identidad -------------------------------------------------------
    @property
    def label(self) -> str:
        """Nombre visible por defecto: ``issuer:name`` sin duplicar el issuer."""
        if self.issuer and self.name and not self.name.startswith(self.issuer + ":"):
            return f"{self.issuer}:{self.name}"
        return self.name or self.issuer

    # --- códigos ----------------------------------------------------------
    def code(self, at: float | None = None) -> str:
        if self.type == "hotp":
            return hotp(self.secret, self.counter, self.digits, self.algorithm)
        t = time.time() if at is None else at
        return hotp(self.secret, int(t // self.period), self.digits, self.algorithm)

    def remaining(self, at: float | None = None) -> int:
        """Segundos de validez que le quedan al código TOTP actual."""
        t = time.time() if at is None else at
        return self.period - int(t % self.period)

    # --- URI ---------------------------------------------------------------
    def to_uri(self) -> str:
        params = {"secret": b32encode(self.secret)}
        if self.issuer:
            params["issuer"] = self.issuer
        if self.algorithm != "SHA1":
            params["algorithm"] = self.algorithm
        if self.digits != 6:
            params["digits"] = str(self.digits)
        if self.type == "totp" and self.period != 30:
            params["period"] = str(self.period)
        if self.type == "hotp":
            params["counter"] = str(self.counter)
        return f"otpauth://{self.type}/{quote(self.label, safe=':@')}?{urlencode(params, quote_via=quote)}"

    @classmethod
    def from_uri(cls, uri: str) -> Account:
        parts = urlsplit(uri.strip())
        if parts.scheme.lower() != "otpauth":
            raise OtpError("no es una URI otpauth://")
        otp_type = parts.netloc.lower()
        q = {k.lower(): v[-1] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        if "secret" not in q:
            raise OtpError("falta el parámetro secret")
        label = unquote(parts.path.lstrip("/"))
        issuer = q.get("issuer", "")
        name = label
        if ":" in label:
            prefix, rest = label.split(":", 1)
            issuer = issuer or prefix.strip()
            name = rest.strip()
        try:
            return cls(
                secret=b32decode(q["secret"]),
                name=name,
                issuer=issuer,
                type=otp_type,
                algorithm=q.get("algorithm", "SHA1").upper(),
                digits=int(q.get("digits", 6)),
                period=int(q.get("period", 30)),
                counter=int(q.get("counter", 0)),
            )
        except ValueError as e:
            if isinstance(e, OtpError):
                raise
            raise OtpError(f"parámetro numérico no válido: {e}") from None

    def with_counter(self, counter: int) -> Account:
        return replace(self, counter=counter)


def hotp(secret: bytes, counter: int, digits: int = 6, algorithm: str = "SHA1") -> str:
    """RFC 4226."""
    mac = hmac.new(secret, struct.pack(">Q", counter), ALGORITHMS[algorithm]).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)
