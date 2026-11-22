# otprunner

Gestor de códigos TOTP integrado en el lanzador del escritorio (KRunner en KDE Plasma),
con los secretos guardados en el keystore del sistema y CLI equivalente.

> Estado: en rediseño. Ver [Hoja de ruta](#hoja-de-ruta).

## Características

- Muestra y copia códigos TOTP desde KRunner (`otp <filtro>`) o desde la consola.
- Secretos en el keystore del sistema, el que haya: Secret Service (GNOME Keyring,
  KeePassXC, KWallet ≥ KF 5.97) o KWallet nativo. Nunca en ficheros planos.
- Alta de cuentas sin abrir consola: captura de una zona de pantalla con el QR,
  portapapeles o (más adelante) cámara.
- Import y export en formato `otpauth://` y `otpauth-migration://` (Google Authenticator),
  incluido export como QR para pasar cuentas al móvil.
- Funciona en Plasma 5.27 y 6, X11 y Wayland; usa la herramienta disponible en cada caso
  (portal XDG, spectacle, Klipper, wl-copy, xclip…). `otprunner doctor` dice qué usa y qué falta.

## Uso

### KRunner

| Escribes | Acción |
|---|---|
| `otp` / `otp <filtro>` | Lista códigos; Enter copia el código |
| `otp add [nombre]` | Captura de pantalla · portapapeles · cámara |
| `otp export [filtro]` | Muestra QR de migración (pide confirmación) |
| `otp rm <nombre>` | Borra la cuenta (pide confirmación) |
| `otp rename <viejo> <nuevo>` | Renombra |

La palabra clave es configurable; `otpr` se acepta como alias.

### CLI

```
otprunner list [filtro]
otprunner code <nombre> [--copy]
otprunner add [nombre] --screen | --camera | --clipboard | --uri URI
otprunner import <fichero|URI>
otprunner export [filtro] [--qr | --uri]
otprunner rm <nombre>
otprunner rename <viejo> <nuevo>
otprunner install | uninstall | doctor
```

## Instalación

```bash
pipx install .        # o: uv tool install .
otprunner install     # registra el runner en KRunner y la unidad systemd de usuario
otprunner doctor      # comprueba keystore, portapapeles, captura, etc.
```

`otprunner uninstall` deshace lo anterior. Los secretos permanecen en el keystore.

### Dependencias del sistema (opcionales, según escritorio)

- Captura de pantalla: portal XDG (normalmente ya presente), o `spectacle` / `gnome-screenshot` / `maim`.
- Portapapeles: Klipper (KDE), o `wl-clipboard` (Wayland) / `xclip` (X11).
- Confirmaciones: `kdialog` o `zenity`.
- Cámara: `zbar-tools` (`zbarcam`).

## Configuración

Opcional, en `~/.config/otprunner/config.toml` (tras cambiar `keywords`, repite `otprunner install`):

```toml
backend = "auto"            # auto | secretservice | kwallet
keywords = ["otp", "otpr"]  # palabras clave en KRunner
idle_timeout = 600          # segundos sin uso antes de cerrar el servicio (0 = nunca)
```

## Cómo funciona

- KRunner habla con el runner por DBus (`org.kde.krunner1`). El servicio se activa por DBus,
  que delega en una unidad systemd de usuario: logs en `journalctl --user -u otprunner`.
- El servicio cachea las cuentas durante la sesión de KRunner y se cierra tras
  `idle_timeout` segundos sin uso: los secretos no se quedan en memoria indefinidamente.
- Cada cuenta es un item del keystore con atributos `application=otprunner` y
  `account=<nombre>`; el secreto es la URI `otpauth://` completa.

## Desarrollo

```bash
uv venv && uv pip install -e '.[dev]'
pytest
```

Para depurar el runner: `systemctl --user stop otprunner` y lanzar `otprunner serve -v`
en una terminal; KRunner hablará con ese proceso.

Referencias recopiladas: [docs/referencias.md](docs/referencias.md).

## Hoja de ruta

0. ~~Limpieza del repo~~
1. ~~Núcleo: modelo `otpauth`, códec `otpauth-migration`, keystores, `doctor`~~
2. ~~Runner DBus (`list`/copiar), unidad systemd, `install`~~
3. `add` por captura de pantalla y portapapeles; `import`
4. `export` (QR/URI), `rm`, `rename`
5. Cámara (varios proveedores)
6. (Opcional) Frontend GNOME Shell search provider
