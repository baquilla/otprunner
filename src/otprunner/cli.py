"""CLI de OTPRunner. Mismos comandos que el runner de KRunner."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from . import APP_NAME, __version__, config, exporting, i18n, importer, migration
from .camera import CameraError
from .capture import CaptureError
from .i18n import _
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
        raise StoreError(_("no account matches “{filter}”").format(filter=pattern))
    raise StoreError(_("“{filter}” is ambiguous: {matches}").format(filter=pattern, matches=", ".join(hits)))


def _read_source(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    if src.lower().startswith(("otpauth://", "otpauth-migration://")):
        return src
    with open(src, encoding="utf-8") as f:
        return f.read()


def _report(res: importer.ImportResult, errors: list[str]) -> int:
    for n in res.added:
        print(_("added: {name}").format(name=n))
    for wanted, final in res.renamed:
        print("  " + _("(“{wanted}” already existed, saved as “{final}”)").format(wanted=wanted, final=final))
    for n in res.updated:
        print(_("updated (same secret, name kept): {name}").format(name=n))
    for n in res.skipped:
        print(_("skipped (already present with the same secret): {name}").format(name=n))
    for e in errors:
        print(_("error: {message}").format(message=e), file=sys.stderr)
    return 1 if errors and not (res.added or res.updated) else 0


async def _cmd(args, cfg) -> int:
    if args.cmd == "doctor":
        from . import doctor

        return await doctor.run()

    if args.cmd == "serve":
        from . import runner

        return await runner.serve(idle_timeout=args.idle, demo=args.demo)

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
                print(_("copied to the clipboard ({provider})").format(provider=provider), file=sys.stderr)
            return 0

        if args.cmd == "add":
            from . import adding, capture
            from .dbusutil import session_bus

            source = "uri" if args.uri else "clipboard" if args.clipboard else "camera" if args.camera else "screen"
            if source == "screen":
                print(_("Select the area of the screen with the QR code…"), file=sys.stderr)
            elif source == "camera":
                print(_("Show the QR code to the camera (close the window to cancel)…"), file=sys.stderr)
            bus = await session_bus()
            try:
                outcome = await adding.add(
                    store,
                    source,
                    bus,
                    name=args.name,
                    uri=args.uri,
                    device=cfg.camera,
                    progress=lambda msg: print(msg, file=sys.stderr),
                )
            except capture.CaptureCancelled:
                print(_("cancelled"), file=sys.stderr)
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
                print(_("error: no otpauth URI found"), file=sys.stderr)
                return 1
            res = await importer.import_accounts(store, parsed.accounts)
            return _report(res, parsed.errors)

        if args.cmd == "export":
            accounts = await store.all()
            names = _match(accounts, args.filter)
            if not names:
                print(_("no accounts to export"), file=sys.stderr)
                return 1
            if args.format == "otpauth" or (args.format == "auto" and len(names) == 1):
                for n in names:
                    if args.qr:
                        print(n)
                        exporting.terminal(accounts[n].to_uri())
                    else:
                        print(accounts[n].to_uri())
                return 0
            exp = exporting.build(
                {n: accounts[n] for n in names}, batch_size=args.batch, single_otpauth=args.format == "auto"
            )
            for n, reason in exp.skipped:
                print(
                    _("skipped {name}: {reason} (use --format otpauth)").format(name=n, reason=reason), file=sys.stderr
                )
            for i, uri in enumerate(exp.uris, 1):
                if args.qr:
                    print(_("QR {i} of {n}").format(i=i, n=len(exp.uris)))
                    exporting.terminal(uri)
                else:
                    print(uri)
            return 0 if exp.uris else 1

        if args.cmd in ("remove", "rm"):
            name = _resolve(await store.names(), args.name)
            if not args.yes:
                ans = input(_("Remove “{name}”? [y/N] ").format(name=name)).strip().lower()
                if ans not in ("y", "yes", _("y"), _("yes")):
                    print(_("cancelled"))
                    return 1
            await store.delete(name)
            print(_("removed: {name}").format(name=name))
            return 0

        if args.cmd == "rename":
            old = _resolve(await store.names(), args.old)
            await store.rename(old, args.new)
            print(_("renamed: {old} → {new}").format(old=old, new=args.new))
            return 0
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="otprunner",
        description=_("{app}: TOTP codes with the secrets in the system keystore.").format(app=APP_NAME),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--backend", help=_("keystore: auto, kwallet, secretservice (default: from the config)"))
    sub = p.add_subparsers(dest="cmd", required=True, metavar=_("COMMAND"))

    s = sub.add_parser("list", help=_("list accounts and codes"))
    s.add_argument("filter", nargs="?")
    s.add_argument("--names", action="store_true", help=_("names only"))

    s = sub.add_parser("code", help=_("show the code of an account"))
    s.add_argument("name")
    s.add_argument("-c", "--copy", action="store_true", help=_("also copy it to the clipboard"))

    s = sub.add_parser("add", help=_("add an account"))
    s.add_argument("name", nargs="?", help=_("name (default: issuer:account from the QR code)"))
    g = s.add_mutually_exclusive_group()
    g.add_argument("--screen", action="store_true", help=_("QR code in an area of the screen (default)"))
    g.add_argument("--clipboard", action="store_true", help=_("URI or QR image from the clipboard"))
    g.add_argument("--camera", action="store_true", help=_("QR code shown to the camera"))
    g.add_argument("--uri", help=_("otpauth:// or otpauth-migration:// URI"))

    s = sub.add_parser("import", help=_("import otpauth/otpauth-migration URIs from a file, '-' or the URI itself"))
    s.add_argument("source")

    s = sub.add_parser("export", help=_("export accounts"))
    s.add_argument("filter", nargs="?")
    s.add_argument(
        "--format",
        choices=("auto", "migration", "otpauth"),
        default="auto",
        help=_("auto: otpauth for a single account, migration for several"),
    )
    s.add_argument("--batch", type=int, default=migration.DEFAULT_BATCH, help=_("accounts per migration URI"))
    s.add_argument("--qr", action="store_true", help=_("show as QR codes in the terminal"))

    s = sub.add_parser("remove", aliases=["rm"], help=_("remove an account"))
    s.add_argument("name")
    s.add_argument("-y", "--yes", action="store_true", help=_("do not ask for confirmation"))

    s = sub.add_parser("rename", help=_("rename an account"))
    s.add_argument("old")
    s.add_argument("new")

    sub.add_parser("doctor", help=_("diagnose the environment"))
    sub.add_parser("install", help=_("register the runner in KRunner (and the systemd user unit)"))
    sub.add_parser("uninstall", help=_("undo install (the secrets are kept)"))

    s = sub.add_parser("serve", help=_("run the runner DBus service (started by DBus/systemd)"))
    s.add_argument("-v", "--verbose", action="store_true", help=_("debug logging"))
    s.add_argument("--idle", type=float, help=_("idle seconds before exiting (0 = never)"))
    s.add_argument(
        "--demo", action="store_true", help=_("serve made-up accounts instead of the keystore (for screenshots)")
    )
    return p


def main(argv: list[str] | None = None) -> int:
    cfg = config.load()
    i18n.setup(cfg.language)
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
        return asyncio.run(_cmd(args, cfg))
    except (StoreError, OtpError, CaptureError, CameraError, OSError) as e:
        print(_("error: {message}").format(message=e), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
