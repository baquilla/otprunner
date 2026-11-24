"""Runner de KRunner por DBus (interfaz org.kde.krunner1).

El servicio se activa por DBus (vía systemd de usuario si existe), cachea las cuentas
mientras dura la sesión de KRunner y se cierra solo tras un rato sin uso, de modo que
los secretos no se quedan en memoria indefinidamente.
"""

import asyncio
import contextlib
import logging
import time

from dbus_fast import Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import RequestNameReply
from dbus_fast.service import ServiceInterface, method

from . import APP_NAME, adding, camera, capture, clipboard, config, dialogs, exporting, i18n
from .dbusutil import call
from .i18n import _, ngettext
from .notify import notify
from .otpauth import Account, OtpError
from .store import Store, StoreError, open_store

log = logging.getLogger(__name__)

# Identificador inverso del proyecto (sirve también como app-id de Flathub).
BUS_NAME = "io.github.baquilla.otprunner"
ICON = "otprunner"  # instalado en hicolor por «otprunner install»
OBJECT_PATH = "/runner"

# Plasma::QueryMatch::Type
EXACT, POSSIBLE, INFORMATIONAL = 100, 30, 50
SEP = "\x1f"
# Cabecera de grupo en KRunner.
CATEGORY = APP_NAME
# KRunner (Milou) muestra como mucho 15 resultados, repartidos entre los runners que
# respondan; recortamos a ``max_results`` para que los comandos y el «hay más» quepan.
# Subcomandos en el orden en que se sugieren; «rm» es alias de «remove».
COMMANDS = ("add", "rename", "remove", "export")
ALIASES = {"rm": "remove"}


def fmt_code(code: str) -> str:
    """123456 → «123 456»; 12345678 → «1234 5678»."""
    half = len(code) // 2
    return f"{code[:half]} {code[half:]}"


class Runner:
    """Lógica independiente de DBus (testeable con MemoryStore)."""

    def __init__(self, cfg: config.Config, store_factory, bus=None, cache_ttl: float = 60.0) -> None:
        self.cfg = cfg
        self.store_factory = store_factory
        self.bus = bus
        self.cache_ttl = cache_ttl
        self._store: Store | None = None
        self._cache: dict[str, Account] | None = None
        self._cache_at = 0.0
        self._lock = asyncio.Lock()
        self.last_activity = time.monotonic()

    # --- consultas ----------------------------------------------------------
    def parse(self, query: str) -> str | None:
        """Devuelve el filtro si la consulta es nuestra, o None."""
        q = query.strip()
        head, _sep, rest = q.partition(" ")
        if head.casefold() in (k.casefold() for k in self.cfg.keywords):
            return rest.strip()
        return None

    async def _get_store(self) -> Store:
        if self._store is None:
            self._store = await self.store_factory()
        return self._store

    async def accounts(self, refresh: bool = False) -> dict[str, Account]:
        async with self._lock:  # una sola carga (y un solo diálogo de desbloqueo) a la vez
            fresh = self._cache is not None and time.monotonic() - self._cache_at < self.cache_ttl
            if fresh and not refresh:
                return self._cache
            try:
                self._cache = await (await self._get_store()).all()
            except Exception:
                await self.reset_store()
                raise
            self._cache_at = time.monotonic()
            return self._cache

    async def reset_store(self) -> None:
        if self._store is not None:
            with contextlib.suppress(Exception):
                await self._store.close()
        self._store = None

    def forget(self) -> None:
        self._cache = None

    def _no_match(self, accounts: dict, flt: str) -> tuple:
        if not accounts:
            text = _("No accounts yet")
        else:
            text = _("No account matches “{filter}”").format(filter=flt)
        # EXACT y en nuestra categoría: si no, KRunner la pone aparte y debajo de los comandos.
        return ("none", text, "dialog-information", EXACT, 0.5, {"category": CATEGORY})

    async def match(self, query: str) -> list:
        flt = self.parse(query)
        if flt is None:
            return []
        self.last_activity = time.monotonic()
        try:
            accounts = await self.accounts()
        except (StoreError, OtpError) as e:
            return [
                (
                    "error",
                    f"{APP_NAME}: {e}",
                    "dialog-error",
                    EXACT,
                    1.0,
                    {"subtext": _("Keystore"), "category": CATEGORY},
                )
            ]
        cmd, _sep, arg = flt.partition(" ")
        cmd = ALIASES.get(cmd.casefold(), cmd.casefold())
        if cmd == "add":
            return self._add_matches(arg.strip())
        if cmd in ("export", "remove", "rename"):
            return self._manage_matches(cmd, arg.strip(), accounts)
        if not flt:
            return [self._search_hint(len(accounts)), *self._command_matches(COMMANDS)]
        f = flt.casefold()
        names = [n for n in accounts if f in n.casefold()]
        cmds = [c for c in COMMANDS if c.startswith(f)]
        if not names:
            return [self._no_match(accounts, flt), *self._command_matches(cmds or ["add"])]
        names, more = self._fit(names, self.cfg.max_results - len(cmds))
        now = time.time()
        out = []
        for i, name in enumerate(names):
            a = accounts[name]
            # KRunner no refresca los resultados mientras no cambie la consulta, así que
            # mostramos datos que siguen siendo ciertos: hasta cuándo vale y el siguiente.
            # Enter copia siempre el código vigente (se calcula en Run).
            mode = self.cfg.show_codes
            if a.type == "hotp":
                text, sub = name, _("HOTP: Enter generates and copies the next code")
            elif mode == "always":
                expires = now + a.remaining(now)
                text = f"{fmt_code(a.code(now))}   {name}"
                sub = _("valid until {time}  ·  next: {code}").format(
                    time=time.strftime("%H:%M:%S", time.localtime(expires)), code=fmt_code(a.code(expires))
                )
            elif mode == "selected":
                # Plasma 5 solo muestra el subtítulo de la línea seleccionada.
                text, sub = name, fmt_code(a.code(now))
            else:  # never
                text, sub = name, _("Enter copies the code")
            exact = name.casefold() == f
            relevance = 1.0 if exact else max(0.5, 0.99 - i * 0.001)
            out.append((f"code{SEP}{name}", text, ICON, EXACT, relevance, {"subtext": sub, "category": CATEGORY}))
        return out + self._more(more, flt) + self._command_matches(cmds)

    # --- ayudas de navegación ---------------------------------------------------
    @staticmethod
    def _fit(names: list[str], slots: int) -> tuple[list[str], int]:
        """Recorta a ``slots`` entradas, reservando una para «+N más» si hace falta."""
        if len(names) <= slots:
            return names, 0
        keep = max(1, slots - 1)
        return names[:keep], len(names) - keep

    def _more(self, more: int, flt: str) -> list:
        if not more:
            return []
        text = ngettext(
            "+{n} more: type more letters to narrow it down", "+{n} more: type more letters to narrow it down", more
        ).format(n=more)
        return [(f"query{SEP}{self.cfg.keywords[0]} {flt}", text, "go-down-search", EXACT, 0.4, {"category": CATEGORY})]

    def _search_hint(self, n: int) -> tuple:
        kw = self.cfg.keywords[0]
        text = ngettext("Type to search your {n} account", "Type to search your {n} accounts", n).format(n=n)
        return (
            f"query{SEP}{kw} ",
            text,
            "search",
            EXACT,
            0.5,
            {"subtext": _("{keyword} <filter>").format(keyword=kw), "category": CATEGORY},
        )

    def _command_matches(self, cmds) -> list:
        """Sugerencias de subcomando; al elegirlas, KRunner se reabre con «otp <cmd> »."""
        kw = self.cfg.keywords[0]
        info = {
            "add": (
                _("Add an account"),
                "list-add",
                _("{keyword} add [name]  ·  from the screen, the clipboard or the camera"),
            ),
            "rename": (_("Rename an account"), "edit-rename", _("{keyword} rename [filter]")),
            "remove": (_("Remove an account"), "edit-delete", _("{keyword} remove [filter]")),
            "export": (_("Export accounts as QR codes"), "document-export", _("{keyword} export [filter]")),
        }
        out = []
        for j, c in enumerate(cmds):
            text, icon, sub = info[c]
            out.append(
                (
                    f"query{SEP}{kw} {c} ",
                    text,
                    icon,
                    EXACT,
                    0.3 - j * 0.01,
                    {"subtext": sub.format(keyword=kw), "category": CATEGORY},
                )
            )
        return out

    def _manage_matches(self, cmd: str, flt: str, accounts: dict) -> list:
        f = flt.casefold()
        names = [n for n in accounts if f in n.casefold()]
        if not names:
            return [self._no_match(accounts, flt)]
        if cmd == "export":
            text = ngettext(
                "Export {n} account as a QR code for Google Authenticator",
                "Export {n} accounts as QR codes for Google Authenticator",
                len(names),
            ).format(n=len(names))
            sub = _("Shows the secrets on screen (asks for confirmation)")
            if not flt:
                sub += "  ·  " + _("filter with: {keyword} export <text>").format(keyword=self.cfg.keywords[0])
            return [(f"export{SEP}{flt}", text, "document-export", EXACT, 1.0, {"subtext": sub, "category": CATEGORY})]
        if cmd == "remove":
            label, icon, sub = _("Remove “{name}”"), "edit-delete", _("Asks for confirmation")
        else:
            label, icon, sub = _("Rename “{name}”…"), "edit-rename", _("Asks for the new name")
        names, more = self._fit(names, self.cfg.max_results)
        return [
            (
                f"{cmd}{SEP}{n}",
                label.format(name=n),
                icon,
                EXACT,
                max(0.5, 0.99 - i * 0.001),
                {"subtext": sub, "category": CATEGORY},
            )
            for i, n in enumerate(names)
        ] + self._more(more, f"{cmd} {flt}".strip())

    async def _manage(self, cmd: str, arg: str) -> None:
        try:
            store = await self._get_store()
            if cmd == "export":
                await self._export(arg)
            elif cmd == "remove":
                text = _(
                    "Remove the account “{name}”?\n\nThis cannot be undone: make sure you have another way to sign in."
                ).format(name=arg)
                if await dialogs.confirm(APP_NAME, text, ok_label=_("Remove")) and await store.delete(arg):
                    await notify(self.bus, _("Removed: {name}").format(name=arg))
            elif cmd == "rename":
                new = await dialogs.ask_text(APP_NAME, _("New name for “{name}”:").format(name=arg), arg)
                if new and new != arg:
                    await store.rename(arg, new)
                    await notify(self.bus, _("Renamed: {old} → {new}").format(old=arg, new=new))
        except Exception as e:
            log.exception("error in %s %s", cmd, arg)
            await notify(
                self.bus,
                _("{app}: could not complete “{command}”").format(app=APP_NAME, command=cmd),
                str(e),
                error=True,
            )
        finally:
            self.forget()

    async def _export(self, flt: str) -> None:
        f = flt.casefold()
        accounts = {n: a for n, a in (await self.accounts(refresh=True)).items() if f in n.casefold()}
        exp = exporting.build(accounts)
        skipped = "\n".join(f"{n}: {r}" for n, r in exp.skipped)
        if not exp.uris:
            await notify(self.bus, _("Nothing to export"), skipped, error=True)
            return
        n = len(exp.uris)
        secrets_txt = ngettext("{n} secret", "{n} secrets", len(exp.exported)).format(n=len(exp.exported))
        codes_txt = ngettext("{n} QR code", "{n} QR codes", n).format(n=n)
        msg = _(
            "{secrets} will be shown on screen in {codes}.\n\nAnyone who sees or photographs the screen "
            "can copy those accounts. Continue?"
        ).format(secrets=secrets_txt, codes=codes_txt)
        if not await dialogs.confirm(_("{app}: export").format(app=APP_NAME), msg, ok_label=_("Show QR")):
            return
        d = capture.private_dir()
        if exp.uris[0].startswith("otpauth://"):
            path = exporting.write_png(exp.uris[0], d)
            title = _("{app}: {name} — scan it with your authenticator app").format(app=APP_NAME, name=exp.exported[0])
        else:
            # Todos a la vez: en la pantalla del PC caben y el móvil los va leyendo en orden.
            captions = [f"{i}/{n}" for i in range(1, n + 1)]
            max_w, max_h = await asyncio.to_thread(dialogs.image_area)
            path = exporting.write_sheet(exp.uris, captions, d, max_width=max_w, max_height=max_h)
            title = ngettext(
                "{app}: scan the QR code with Google Authenticator",
                "{app}: scan the {n} QR codes with Google Authenticator",
                n,
            ).format(app=APP_NAME, n=n)
        try:
            await dialogs.show_image(path, title)
        finally:
            path.unlink(missing_ok=True)
        if exp.skipped:
            await notify(self.bus, _("Some accounts were not exported"), skipped, icon="dialog-warning")

    def _add_matches(self, name: str) -> list:
        if name:
            screen = _("Add “{name}” from a QR code on screen").format(name=name)
            clip = _("Add “{name}” from the clipboard").format(name=name)
            cam = _("Add “{name}” with the camera").format(name=name)
            hint = ""
        else:
            screen = _("Add an account from a QR code on screen")
            clip = _("Add an account from the clipboard")
            cam = _("Add an account with the camera")
            hint = "  ·  " + _("optional name: {keyword} add <name>").format(keyword=self.cfg.keywords[0])
        cam_sub = (
            _("Show the QR code (or those of a Google export) to the camera")
            if camera.providers()
            else _("Requires {hint}").format(hint=camera.install_hint())
        )
        return [
            (
                f"add{SEP}screen{SEP}{name}",
                screen,
                "spectacle",
                EXACT,
                1.0,
                {
                    "subtext": _("Select the area with the QR code (a Google export works too)") + hint,
                    "category": CATEGORY,
                },
            ),
            (
                f"add{SEP}clipboard{SEP}{name}",
                clip,
                "edit-paste",
                EXACT,
                0.9,
                {
                    "subtext": _("otpauth:// or otpauth-migration:// URI, or an image of the QR code") + hint,
                    "category": CATEGORY,
                },
            ),
            (
                f"add{SEP}camera{SEP}{name}",
                cam,
                "camera-web",
                EXACT,
                0.8,
                {"subtext": cam_sub + hint, "category": CATEGORY},
            ),
        ]

    async def _query(self, text: str) -> None:
        if self.bus is None:
            return
        try:
            await call(self.bus, "org.kde.krunner", "/App", "org.kde.krunner.App", "query", "s", [text])
        except Exception as e:
            log.warning("could not reopen KRunner: %s", e)

    async def _add(self, source: str, name: str) -> None:
        try:
            store = await self._get_store()

            def progress(msg: str) -> None:
                if self.bus is not None:
                    asyncio.get_running_loop().create_task(
                        notify(self.bus, APP_NAME, msg, timeout_ms=4000, transient=True)
                    )

            outcome = await adding.add(
                store, source, self.bus, name=name or None, device=self.cfg.camera, progress=progress
            )
        except capture.CaptureCancelled:
            return
        except Exception as e:
            log.exception("error adding from %s", source)
            if self.bus is not None:
                await notify(self.bus, _("{app}: could not add the account").format(app=APP_NAME), str(e), error=True)
            return
        finally:
            self.forget()
        title, body = outcome.summary()
        log.info("added from %s: %s %s", source, title, body.replace("\n", " | "))
        if self.bus is not None:
            await notify(
                self.bus,
                title,
                body,
                icon=ICON if outcome.ok else "dialog-warning",
                error=not outcome.ok and bool(outcome.parsed.errors),
            )

    async def run(self, match_id: str, action_id: str) -> None:
        self.last_activity = time.monotonic()
        kind, _sep, name = match_id.partition(SEP)
        if kind == "query":
            await asyncio.sleep(0.2)  # dejar que KRunner se cierre antes de reabrirlo
            await self._query(name)
            return
        if kind == "add":
            source, _sep, acc_name = name.partition(SEP)
            await self._add(source, acc_name)
            return
        if kind in ("export", "remove", "rename"):
            await self._manage(kind, name)
            return
        if kind != "code":
            return
        try:
            accounts = await self.accounts()
            acc = accounts.get(name)
            if acc is None:
                raise StoreError(_("the account “{name}” no longer exists").format(name=name))
            code = acc.code()
            if acc.type == "hotp":
                store = await self._get_store()
                await store.put(name, acc.with_counter(acc.counter + 1), replace=True)
                self.forget()
            provider = await clipboard.copy(code, self.bus)
            log.info("code for %s copied (%s)", name, provider)
            if self.bus is not None:
                await notify(self.bus, _("Code for {name} copied").format(name=name), timeout_ms=2000, transient=True)
        except Exception as e:
            log.exception("error running %s", name)
            if self.bus is not None:
                await notify(self.bus, _("{app}: could not copy the code").format(app=APP_NAME), str(e), error=True)


class KRunnerInterface(ServiceInterface):
    def __init__(self, runner: Runner) -> None:
        super().__init__("org.kde.krunner1")
        self.runner = runner

    @method()
    async def Match(self, query: "s") -> "a(sssida{sv})":
        try:
            matches = await self.runner.match(query)
        except Exception:
            log.exception("error in Match")
            return []
        return [[i, t, ic, ty, r, {k: Variant("s", v) for k, v in props.items()}] for i, t, ic, ty, r, props in matches]

    @method()
    def Actions(self) -> "a(sss)":
        return []

    @method()
    async def Run(self, match_id: "s", action_id: "s"):
        # No bloquear a KRunner: la copia y la notificación siguen en segundo plano.
        asyncio.get_running_loop().create_task(self.runner.run(match_id, action_id))

    @method()
    def Teardown(self):
        # Fin de la sesión de KRunner: se relee el keystore en la próxima consulta.
        self.runner.forget()


async def serve(idle_timeout: float | None = None, demo: bool = False) -> int:
    cfg = config.load()
    i18n.setup(cfg.language)
    idle = cfg.idle_timeout if idle_timeout is None else idle_timeout
    bus = await MessageBus().connect()
    if demo:
        from . import demo as demo_mod

        fake = demo_mod.store()

        async def factory():
            return fake
    else:

        def factory():
            return open_store(cfg.backend, bus=bus)

    runner = Runner(cfg, factory, bus=bus)
    bus.export(OBJECT_PATH, KRunnerInterface(runner))
    reply = await bus.request_name(BUS_NAME)
    if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
        log.error("%s is already owned by another process", BUS_NAME)
        bus.disconnect()
        return 1
    log.info(
        "listening on %s%s (keywords: %s, idle exit after %ss)",
        BUS_NAME,
        OBJECT_PATH,
        ", ".join(cfg.keywords),
        idle or "∞",
    )

    disconnected = asyncio.ensure_future(bus.wait_for_disconnect())
    try:
        while not disconnected.done():
            await asyncio.wait([disconnected], timeout=15)
            if idle and time.monotonic() - runner.last_activity > idle:
                log.info("idle for %ss: exiting (DBus will start it again)", idle)
                break
    finally:
        await runner.reset_store()
        if not disconnected.done():
            bus.disconnect()
    return 0
