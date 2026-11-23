"""CLI de otprunner. Mismos comandos que el runner de KRunner."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from . import APP_NAME, __version__, config, exporting, importer, migration
from .camera import CameraError
from .capture import CaptureError
from .otpauth import OtpError
from .store import StoreError, open_store


def _match(names, pattern: str | None) -> list[str]:
    if not pattern:
        return list(names)
    p = pattern.casefold()
    return [n for n in names if p in n.casefold()]


def _resolve(names, pattern: str) -> str:
    """Nombre exacto, o el único que contiene ``pattern``."""
    if pattern in names:
        return pattern
    hits = _match(names, pattern)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise StoreError(f"no hay ninguna cuenta que coincida con «{pattern}»")
    raise StoreError(f"«{pattern}» es ambiguo: {', '.join(hits)}")


def _read_source(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    if src.lower().startswith(("otpauth://", "otpauth-migration://")):
        return src
    with open(src, encoding="utf-8") as f:
        return f.read()


def _report(res: importer.ImportResult, errors: list[str]) -> int:
    for n in res.added:
        print(f"añadida: {n}")
    for wanted, final in res.renamed:
        print(f"  («{wanted}» ya existía, guardada como «{final}»)")
    for n in res.skipped:
        print(f"omitida (ya existe con el mismo secreto): {n}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if errors and not res.added else 0


async def _cmd(args, cfg) -> int:
    if args.cmd == "doctor":
        from . import doctor

        return await doctor.run()

    if args.cmd == "serve":
        from . import runner

        return await runner.serve(idle_timeout=args.idle)

    async with await open_store(args.backend or cfg.backend) as store:
        if args.cmd == "list":
            accounts = await store.all()
            names = _match(accounts, args.filter)
            if args.names:
                print("\n".join(names))
                return 0
            now = time.time()
            width = max((len(n) for n in names), default=0)
            for n in names:
                a = accounts[n]
                extra = f"{a.remaining(now):>3}s" if a.type == "totp" else "hotp"
                print(f"{n:<{width}}  {a.code(now)}  {extra}")
            return 0

        if args.cmd == "code":
            accounts = await store.all()
            name = _resolve(accounts, args.name)
            acc = accounts[name]
            code = acc.code()
            if acc.type == "hotp":
                await store.put(name, acc.with_counter(acc.counter + 1), replace=True)
            print(code)
            if args.copy:
                from . import clipboard
                from .dbusutil import session_bus

                bus = await session_bus()
                try:
                    provider = await clipboard.copy(code, bus)
                finally:
                    bus.disconnect()
                print(f"copiado al portapapeles ({provider})", file=sys.stderr)
            return 0

        if args.cmd == "add":
            from . import adding, capture
            from .dbusutil import session_bus

            source = "uri" if args.uri else "clipboard" if args.clipboard else "camera" if args.camera else "screen"
            if source == "screen":
                print("Selecciona la zona de la pantalla con el QR…", file=sys.stderr)
            elif source == "camera":
                print("Enseña el QR a la cámara (cierra la ventana para cancelar)…", file=sys.stderr)
            bus = await session_bus()
            try:
                outcome = await adding.add(store, source, bus, name=args.name, uri=args.uri, device=cfg.camera,
                                           progress=lambda msg: print(msg, file=sys.stderr))
            except capture.CaptureCancelled:
                print("cancelado", file=sys.stderr)
                return 1
            finally:
                bus.disconnect()
            title, body = outcome.summary()
            print(title)
            if body:
                print(body)
            return 0 if outcome.ok else 1

        if args.cmd == "import":
            parsed = importer.parse_text(_read_source(args.source))
            if not parsed.accounts and not parsed.errors:
                print("error: no se encontró ninguna URI otpauth", file=sys.stderr)
                return 1
            res = await importer.import_accounts(store, parsed.accounts)
            return _report(res, parsed.errors)

        if args.cmd == "export":
            accounts = await store.all()
            names = _match(accounts, args.filter)
            if not names:
                print("no hay cuentas que exportar", file=sys.stderr)
                return 1
            if args.format == "otpauth":
                for n in names:
                    if args.qr:
                        print(n)
                        exporting.terminal(accounts[n].to_uri())
                    else:
                        print(accounts[n].to_uri())
                return 0
            exp = exporting.build({n: accounts[n] for n in names}, batch_size=args.batch)
            for n, reason in exp.skipped:
                print(f"omitida {n}: {reason} (usa --format otpauth)", file=sys.stderr)
            for i, uri in enumerate(exp.uris, 1):
                if args.qr:
                    print(f"QR {i} de {len(exp.uris)}")
                    exporting.terminal(uri)
                else:
                    print(uri)
            return 0 if exp.uris else 1

        if args.cmd == "rm":
            name = _resolve(await store.names(), args.name)
            if not args.yes:
                ans = input(f"¿Borrar «{name}»? [s/N] ").strip().lower()
                if ans not in ("s", "si", "sí", "y", "yes"):
                    print("cancelado")
                    return 1
            await store.delete(name)
            print(f"borrada: {name}")
            return 0

        if args.cmd == "rename":
            old = _resolve(await store.names(), args.old)
            await store.rename(old, args.new)
            print(f"renombrada: {old} → {args.new}")
            return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="otprunner", description=f"{APP_NAME}: códigos TOTP con secretos en el keystore del sistema.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--backend", help="keystore: auto, secretservice, kwallet (por defecto, el de la config)")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="COMANDO")

    s = sub.add_parser("list", help="lista cuentas y códigos")
    s.add_argument("filter", nargs="?")
    s.add_argument("--names", action="store_true", help="solo nombres")

    s = sub.add_parser("code", help="muestra el código de una cuenta")
    s.add_argument("name")
    s.add_argument("-c", "--copy", action="store_true", help="copiarlo también al portapapeles")

    s = sub.add_parser("add", help="añade una cuenta")
    s.add_argument("name", nargs="?", help="nombre (por defecto, issuer:cuenta del QR)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--screen", action="store_true", help="QR en una zona de la pantalla (por defecto)")
    g.add_argument("--clipboard", action="store_true", help="URI o imagen QR del portapapeles")
    g.add_argument("--camera", action="store_true", help="QR enseñado a la cámara")
    g.add_argument("--uri", help="URI otpauth:// u otpauth-migration://")

    s = sub.add_parser("import", help="importa URIs otpauth/otpauth-migration de un fichero, '-' o la URI misma")
    s.add_argument("source")

    s = sub.add_parser("export", help="exporta cuentas")
    s.add_argument("filter", nargs="?")
    s.add_argument("--format", choices=("migration", "otpauth"), default="migration")
    s.add_argument("--batch", type=int, default=migration.DEFAULT_BATCH, help="cuentas por URI de migración")
    s.add_argument("--qr", action="store_true", help="mostrar como QR en la terminal")

    s = sub.add_parser("rm", help="borra una cuenta")
    s.add_argument("name")
    s.add_argument("-y", "--yes", action="store_true", help="no pedir confirmación")

    s = sub.add_parser("rename", help="renombra una cuenta")
    s.add_argument("old")
    s.add_argument("new")

    sub.add_parser("doctor", help="diagnostica el entorno")
    sub.add_parser("install", help="registra el runner en KRunner (y la unidad systemd de usuario)")
    sub.add_parser("uninstall", help="deshace install (los secretos se conservan)")

    s = sub.add_parser("serve", help="ejecuta el servicio DBus del runner (lo lanza DBus/systemd)")
    s.add_argument("-v", "--verbose", action="store_true", help="log de depuración")
    s.add_argument("--idle", type=float, help="segundos sin uso antes de salir (0 = nunca)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd in ("install", "uninstall"):
        from . import install

        return install.install() if args.cmd == "install" else install.uninstall()
    if args.cmd == "serve":
        import logging

        logging.basicConfig(
            level=logging.DEBUG if args.verbose else logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )
    try:
        return asyncio.run(_cmd(args, config.load()))
    except (StoreError, OtpError, CaptureError, CameraError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
