#!/usr/bin/env python3
"""Vuelca la estructura de URIs ``otpauth-migration://`` sin mostrar secretos.

Sirve para comparar una exportación de Google Authenticator con la que genera OTPRunner:
muestra cada campo protobuf (número, tipo de cable y valor o longitud). Los secretos nunca
se muestran; nombres e issuers solo con ``--names``.

    zbarcam --raw -1 /dev/video0 | scripts/migration-dump.py
    scripts/migration-dump.py 'otpauth-migration://offline?data=…'
"""

from __future__ import annotations

import base64
import sys
from urllib.parse import parse_qs, urlsplit

TOP = {1: "otp_parameters", 2: "version", 3: "batch_size", 4: "batch_index", 5: "batch_id"}
OTP = {1: "secret", 2: "name", 3: "issuer", 4: "algorithm", 5: "digits", 6: "type", 7: "counter"}


def varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def fields(b: bytes):
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = varint(b, i)
            yield num, wt, v, i
        elif wt == 2:
            n, i = varint(b, i)
            yield num, wt, b[i : i + n], i
            i += n
        elif wt == 1:
            yield num, wt, b[i : i + 8], i
            i += 8
        elif wt == 5:
            yield num, wt, b[i : i + 4], i
            i += 4
        else:
            raise ValueError(f"tipo de cable {wt} en el byte {i}")


def dump(uri: str, names: bool) -> None:
    q = parse_qs(urlsplit(uri.strip()).query)
    raw = q["data"][0]
    print(f"URI: {len(uri.strip())} caracteres; data base64: {len(raw)} (padding {'sí' if raw.endswith('=') else 'no'}, "
          f"«+» {'sí' if '+' in raw else 'no'}, «%» en la URI {'sí' if '%' in uri else 'no'})")
    payload = base64.b64decode(raw + "=" * (-len(raw) % 4))
    print(f"payload: {len(payload)} bytes")
    for num, wt, v, _pos in fields(payload):
        label = TOP.get(num, f"¿campo {num}?")
        if num == 1 and wt == 2:
            print(f"  [{num}] {label} ({len(v)} bytes)")
            for n2, wt2, v2, _p2 in fields(v):
                l2 = OTP.get(n2, f"¿campo {n2}?")
                if wt2 == 0:
                    print(f"      [{n2}] {l2} = {v2}")
                elif n2 in (2, 3) and names:
                    print(f"      [{n2}] {l2} = {v2.decode('utf-8', 'replace')!r}")
                else:
                    print(f"      [{n2}] {l2}: {len(v2)} bytes (wt {wt2})")
        else:
            shown = v if wt == 0 else f"{len(v)} bytes (wt {wt})"
            print(f"  [{num}] {label} = {shown}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--names"]
    names = "--names" in sys.argv
    uris = args or [line for line in sys.stdin if "otpauth-migration" in line]
    for uri in uris:
        uri = uri.strip()
        if uri.startswith("QR-Code:"):
            uri = uri[len("QR-Code:"):]
        dump(uri, names)
        print()


if __name__ == "__main__":
    main()
