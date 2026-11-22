"""Runner de KRunner por DBus (interfaz org.kde.krunner1).

El servicio se activa por DBus (vía systemd de usuario si existe), cachea las cuentas
mientras dura la sesión de KRunner y se cierra solo tras un rato sin uso, de modo que
los secretos no se quedan en memoria indefinidamente.
"""

import asyncio
import logging
import time

from dbus_fast import Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import RequestNameReply
from dbus_fast.service import ServiceInterface, method

from . import adding, capture, clipboard, config, dialogs, exporting
from .dbusutil import call
from .notify import notify
from .otpauth import Account, OtpError
from .store import Store, StoreError, open_store

log = logging.getLogger(__name__)

BUS_NAME = "net.bacamt.otprunner"
OBJECT_PATH = "/runner"

# Plasma::QueryMatch::Type
EXACT, POSSIBLE, INFORMATIONAL = 100, 30, 50
SEP = "\x1f"


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
        head, _, rest = q.partition(" ")
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
            try:
                await self._store.close()
            except Exception:  # noqa: BLE001
                pass
        self._store = None

    def forget(self) -> None:
        self._cache = None

    async def match(self, query: str) -> list:
        flt = self.parse(query)
        if flt is None:
            return []
        self.last_activity = time.monotonic()
        try:
            accounts = await self.accounts()
        except (StoreError, OtpError) as e:
            return [("error", f"otprunner: {e}", "dialog-error", INFORMATIONAL, 1.0, {"subtext": "Keystore"})]
        cmd, _, arg = flt.partition(" ")
        if cmd.casefold() == "add":
            return self._add_matches(arg.strip())
        if cmd.casefold() in ("export", "rm", "rename"):
            return self._manage_matches(cmd.casefold(), arg.strip(), accounts)
        f = flt.casefold()
        names = [n for n in accounts if f in n.casefold()]
        if not names:
            text = "No hay cuentas" if not accounts else f"Ninguna cuenta coincide con «{flt}»"
            return [("none", text, "dialog-information", INFORMATIONAL, 0.5, {}),
                    self._helper("add", "Añadir una cuenta…", "list-add")]
        now = time.time()
        out = []
        for i, name in enumerate(names):
            a = accounts[name]
            # KRunner no refresca los resultados mientras no cambie la consulta, así que
            # mostramos datos que siguen siendo ciertos: hasta cuándo vale y el siguiente.
            # Enter copia siempre el código vigente (se calcula en Run).
            mode = self.cfg.show_codes
            if a.type == "hotp":
                text, sub = name, "HOTP: Enter genera y copia el siguiente código"
            elif mode == "always":
                expires = now + a.remaining(now)
                text = f"{fmt_code(a.code(now))}   {name}"
                sub = (f"vale hasta las {time.strftime('%H:%M:%S', time.localtime(expires))}"
                       f"  ·  después: {fmt_code(a.code(expires))}")
            elif mode == "selected":
                # Plasma 5 solo muestra el subtítulo de la línea seleccionada.
                text, sub = name, fmt_code(a.code(now))
            else:  # never
                text, sub = name, "Enter copia el código"
            exact = name.casefold() == f
            relevance = 1.0 if exact else max(0.5, 0.99 - i * 0.001)
            out.append((f"code{SEP}{name}", text, "dialog-password", EXACT, relevance,
                        {"subtext": sub, "category": "OTP"}))
        if not f:
            out.append(self._helper("add", "Añadir una cuenta…", "list-add"))
        return out

    def _helper(self, sub: str, text: str, icon: str) -> tuple:
        """Entrada que completa la consulta en KRunner (p. ej. «otp add »)."""
        kw = self.cfg.keywords[0]
        return (f"query{SEP}{kw} {sub} ", text, icon, POSSIBLE, 0.1,
                {"subtext": f"{kw} add  ·  {kw} export  ·  {kw} rename  ·  {kw} rm", "category": "OTP"})

    def _manage_matches(self, cmd: str, flt: str, accounts: dict) -> list:
        f = flt.casefold()
        names = [n for n in accounts if f in n.casefold()]
        if not names:
            text = "No hay cuentas" if not accounts else f"Ninguna cuenta coincide con «{flt}»"
            return [("none", text, "dialog-information", INFORMATIONAL, 0.5, {})]
        if cmd == "export":
            what = f"{len(names)} cuenta" + ("s" if len(names) != 1 else "")
            hint = "" if flt else f"  ·  filtra con: {self.cfg.keywords[0]} export <texto>"
            return [(f"export{SEP}{flt}", f"Exportar {what} como QR para Google Authenticator",
                     "document-export", EXACT, 1.0,
                     {"subtext": "Muestra los secretos en pantalla (pide confirmación)" + hint, "category": "OTP"})]
        verb, icon = ("Borrar", "edit-delete") if cmd == "rm" else ("Renombrar", "edit-rename")
        dots = "" if cmd == "rm" else "…"
        return [(f"{cmd}{SEP}{n}", f"{verb} «{n}»{dots}", icon, EXACT, max(0.5, 0.99 - i * 0.001),
                 {"subtext": "Pide confirmación" if cmd == "rm" else "Pide el nombre nuevo", "category": "OTP"})
                for i, n in enumerate(names[:20])]

    async def _manage(self, cmd: str, arg: str) -> None:
        try:
            store = await self._get_store()
            if cmd == "export":
                await self._export(arg)
            elif cmd == "rm":
                if await dialogs.confirm("otprunner", f"¿Borrar la cuenta «{arg}»?\n\nNo se puede deshacer: "
                                         "asegúrate de tener otra forma de acceder.", ok_label="Borrar"):
                    if await store.delete(arg):
                        await notify(self.bus, f"Borrada: {arg}", icon="edit-delete")
            elif cmd == "rename":
                new = await dialogs.ask_text("otprunner", f"Nuevo nombre para «{arg}»:", arg)
                if new and new != arg:
                    await store.rename(arg, new)
                    await notify(self.bus, f"Renombrada: {arg} → {new}", icon="edit-rename")
        except Exception as e:  # noqa: BLE001
            log.exception("error en %s %s", cmd, arg)
            await notify(self.bus, f"otprunner: no se pudo completar «{cmd}»", str(e), error=True)
        finally:
            self.forget()

    async def _export(self, flt: str) -> None:
        f = flt.casefold()
        accounts = {n: a for n, a in (await self.accounts(refresh=True)).items() if f in n.casefold()}
        exp = exporting.build(accounts)
        if not exp.uris:
            await notify(self.bus, "Nada que exportar", "\n".join(f"{n}: {r}" for n, r in exp.skipped), error=True)
            return
        n = len(exp.uris)
        msg = (f"Se van a mostrar en pantalla {len(exp.exported)} secretos en {n} código"
               f"{'s' if n > 1 else ''} QR.\n\nCualquiera que vea o fotografíe la pantalla podrá "
               "copiar esas cuentas. ¿Continuar?")
        if not await dialogs.confirm("otprunner: exportar", msg, ok_label="Mostrar QR"):
            return
        d = capture.private_dir()
        for i, uri in enumerate(exp.uris, 1):
            path = exporting.write_png(uri, d)
            try:
                await dialogs.show_image(path, f"otprunner: QR {i} de {n} — escanéalo con Google Authenticator")
            finally:
                path.unlink(missing_ok=True)
        if exp.skipped:
            await notify(self.bus, "Algunas cuentas no se exportaron",
                         "\n".join(f"{n}: {r}" for n, r in exp.skipped), icon="dialog-warning")

    def _add_matches(self, name: str) -> list:
        target = f"«{name}»" if name else "cuenta"
        hint = "" if name else "  ·  nombre opcional: otp add <nombre>"
        return [
            (f"add{SEP}screen{SEP}{name}", f"Añadir {target} desde un QR en pantalla", "spectacle",
             EXACT, 1.0, {"subtext": "Selecciona la zona con el QR (vale una exportación de Google)" + hint,
                          "category": "OTP"}),
            (f"add{SEP}clipboard{SEP}{name}", f"Añadir {target} desde el portapapeles", "edit-paste",
             EXACT, 0.9, {"subtext": "URI otpauth:// u otpauth-migration://, o imagen con el QR" + hint,
                          "category": "OTP"}),
        ]

    async def _query(self, text: str) -> None:
        if self.bus is None:
            return
        try:
            await call(self.bus, "org.kde.krunner", "/App", "org.kde.krunner.App", "query", "s", [text])
        except Exception as e:  # noqa: BLE001
            log.warning("no se pudo reabrir KRunner: %s", e)

    async def _add(self, source: str, name: str) -> None:
        try:
            store = await self._get_store()
            outcome = await adding.add(store, source, self.bus, name=name or None)
        except capture.CaptureCancelled:
            return
        except Exception as e:  # noqa: BLE001
            log.exception("error añadiendo desde %s", source)
            if self.bus is not None:
                await notify(self.bus, "otprunner: no se pudo añadir", str(e), error=True)
            return
        finally:
            self.forget()
        title, body = outcome.summary()
        log.info("alta desde %s: %s %s", source, title, body.replace("\n", " | "))
        if self.bus is not None:
            await notify(self.bus, title, body, icon="list-add" if outcome.ok else "dialog-warning",
                         error=not outcome.ok and bool(outcome.parsed.errors))

    async def run(self, match_id: str, action_id: str) -> None:
        self.last_activity = time.monotonic()
        kind, _, name = match_id.partition(SEP)
        if kind == "query":
            await asyncio.sleep(0.2)  # dejar que KRunner se cierre antes de reabrirlo
            await self._query(name)
            return
        if kind == "add":
            source, _, acc_name = name.partition(SEP)
            await self._add(source, acc_name)
            return
        if kind in ("export", "rm", "rename"):
            await self._manage(kind, name)
            return
        if kind != "code":
            return
        try:
            accounts = await self.accounts()
            acc = accounts.get(name)
            if acc is None:
                raise StoreError(f"la cuenta «{name}» ya no existe")
            code = acc.code()
            if acc.type == "hotp":
                store = await self._get_store()
                await store.put(name, acc.with_counter(acc.counter + 1), replace=True)
                self.forget()
            provider = await clipboard.copy(code, self.bus)
            log.info("código de %s copiado (%s)", name, provider)
            if self.bus is not None:
                await notify(self.bus, f"Código de {name} copiado", icon="edit-paste",
                             timeout_ms=2000, transient=True)
        except Exception as e:  # noqa: BLE001 — el servicio no debe caerse por un Run
            log.exception("error ejecutando %s", name)
            if self.bus is not None:
                await notify(self.bus, "otprunner: no se pudo copiar", str(e), error=True)


class KRunnerInterface(ServiceInterface):
    def __init__(self, runner: Runner) -> None:
        super().__init__("org.kde.krunner1")
        self.runner = runner

    @method()
    async def Match(self, query: "s") -> "a(sssida{sv})":  # noqa: F821
        try:
            matches = await self.runner.match(query)
        except Exception:  # noqa: BLE001
            log.exception("error en Match")
            return []
        return [[i, t, ic, ty, r, {k: Variant("s", v) for k, v in props.items()}]
                for i, t, ic, ty, r, props in matches]

    @method()
    def Actions(self) -> "a(sss)":  # noqa: F821
        return []

    @method()
    async def Run(self, match_id: "s", action_id: "s"):  # noqa: F821
        # No bloquear a KRunner: la copia y la notificación siguen en segundo plano.
        asyncio.get_running_loop().create_task(self.runner.run(match_id, action_id))

    @method()
    def Teardown(self):
        # Fin de la sesión de KRunner: se relee el keystore en la próxima consulta.
        self.runner.forget()


async def serve(idle_timeout: float | None = None) -> int:
    cfg = config.load()
    idle = cfg.idle_timeout if idle_timeout is None else idle_timeout
    bus = await MessageBus().connect()
    runner = Runner(cfg, lambda: open_store(cfg.backend, bus=bus), bus=bus)
    bus.export(OBJECT_PATH, KRunnerInterface(runner))
    reply = await bus.request_name(BUS_NAME)
    if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
        log.error("%s ya está en uso por otro proceso", BUS_NAME)
        bus.disconnect()
        return 1
    log.info("otprunner escuchando en %s%s (palabras clave: %s, cierre tras %ss inactivo)",
             BUS_NAME, OBJECT_PATH, ", ".join(cfg.keywords), idle or "∞")

    disconnected = asyncio.ensure_future(bus.wait_for_disconnect())
    try:
        while not disconnected.done():
            await asyncio.wait([disconnected], timeout=15)
            if idle and time.monotonic() - runner.last_activity > idle:
                log.info("inactivo %ss: saliendo (DBus lo volverá a lanzar)", idle)
                break
    finally:
        await runner.reset_store()
        if not disconnected.done():
            bus.disconnect()
    return 0
