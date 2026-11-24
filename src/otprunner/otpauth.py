"""Modelo de cuenta OTP y formato ``otpauth://`` (Key URI Format de Google Authenticator)."""

from __future__ import annotations

import base64
import re
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass, field, replace
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
from .i18n import _

ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512, "MD5": hashlib.md5}


class OtpError(ValueError):
    """URI o parámetros OTP no válidos."""


def clean_text(s: str) -> str:
    """Quita caracteres de control y espacios sobrantes (hay exportadores que dejan «\\n»)."""
    return " ".join("".join(c for c in s if c.isprintable() or c == " ").split())


def b32decode(secret: str) -> bytes:
    s = secret.replace(" ", "").replace("-", "").upper().rstrip("=")
    try:
        return base64.b32decode(s + "=" * (-len(s) % 8))
    except (ValueError, base64.binascii.Error) as e:
        raise OtpError(_("invalid base32 secret: {error}").format(error=e)) from None


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
    # URI original tal como llegó (vacía si la cuenta viene de otpauth-migration). Es lo que
    # se guarda: nunca se reescribe salvo el contador HOTP.
    uri: str = field(default="", compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.secret:
            raise OtpError(_("empty secret"))
        if self.type not in ("totp", "hotp"):
            raise OtpError(_("unsupported type: {type}").format(type=self.type))
        if self.algorithm not in ALGORITHMS:
            raise OtpError(_("unsupported algorithm: {algorithm}").format(algorithm=self.algorithm))
        if not 6 <= self.digits <= 10:
            raise OtpError(_("invalid digits: {digits}").format(digits=self.digits))
        if self.period <= 0:
            raise OtpError(_("invalid period: {period}").format(period=self.period))

    # --- identidad -------------------------------------------------------
    @property
    def label(self) -> str:
        """Nombre identificador por defecto.

        ``name`` es la etiqueta de la URI tal cual (nunca se parte por «:»). Si hay
        ``issuer`` y la etiqueta no empieza ya por «issuer:», se antepone como prefijo.
        """
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
        """La URI original si la hay; si no, una generada a partir de los campos."""
        if self.uri:
            return self.uri
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
        return f"otpauth://{self.type}/{quote(self.name, safe=':@')}?{urlencode(params, quote_via=quote)}"

    @classmethod
    def from_uri(cls, uri: str) -> Account:
        parts = urlsplit(uri.strip())
        if parts.scheme.lower() != "otpauth":
            raise OtpError(_("not an otpauth:// URI"))
        otp_type = parts.netloc.lower()
        q = {k.lower(): v[-1] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        if "secret" not in q:
            raise OtpError(_("missing secret parameter"))
        # Etiqueta e issuer tal cual llegan; solo se quitan caracteres de control.
        name = clean_text(unquote(parts.path.lstrip("/")))
        issuer = clean_text(q.get("issuer", ""))
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
                uri=uri.strip(),
            )
        except ValueError as e:
            if isinstance(e, OtpError):
                raise
            raise OtpError(_("invalid numeric parameter: {error}").format(error=e)) from None

    def with_counter(self, counter: int) -> Account:
        """Misma cuenta con otro contador HOTP; en la URI original solo cambia ``counter``."""
        uri = self.uri
        if uri:
            uri, n = re.subn(r"([?&]counter=)[^&#]*", lambda m: f"{m.group(1)}{counter}", uri, count=1, flags=re.I)
            if not n:
                uri += f"{'&' if '?' in uri else '?'}counter={counter}"
        return replace(self, counter=counter, uri=uri)


def hotp(secret: bytes, counter: int, digits: int = 6, algorithm: str = "SHA1") -> str:
    """RFC 4226."""
    mac = hmac.new(secret, struct.pack(">Q", counter), ALGORITHMS[algorithm]).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)
