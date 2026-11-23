# OTPRunner

[English](README.md) · **Español**

Códigos TOTP en el lanzador del escritorio (KRunner en KDE Plasma), con los secretos
guardados en el keystore del sistema y una CLI equivalente.

> Estado: versión preliminar (0.2.0.dev0).

## Características

- Busca y copia códigos TOTP desde KRunner (`otp <filtro>`) o desde la consola.
- Secretos en el keystore del sistema, el que haya: en KDE, KWallet (carpeta «otprunner»
  del monedero); en otros escritorios, Secret Service (GNOME Keyring, KeePassXC).
  Nunca en ficheros planos.
- Alta de cuentas sin abrir consola: captura de una zona de pantalla con el QR,
  portapapeles o cámara.
- Import y export en formato `otpauth://` y `otpauth-migration://` (Google Authenticator),
  incluido export como QR para pasar cuentas al móvil.
- Interfaz en inglés y español: sigue el idioma del escritorio (o `language` en la configuración).
- Funciona en Plasma 5.27 y 6, X11 y Wayland; usa la herramienta disponible en cada caso
  (portal XDG, spectacle, Klipper, wl-copy, xclip…). `otprunner doctor` dice qué usa y qué falta.

## Uso

### KRunner

| Escribes | Resultado |
|---|---|
| `otp` | Ayuda de búsqueda y los comandos disponibles (sin códigos) |
| `otp <filtro>` | Cuentas que contienen el texto (Enter copia el código) y, al final, los comandos que empiezan por él: `otp re` → rename, remove |
| `otp add [nombre]` | Añadir desde captura de pantalla · portapapeles · cámara |
| `otp rename [filtro]` | Renombrar (pide el nombre nuevo) |
| `otp remove [filtro]` | Borrar (pide confirmación); `rm` también vale |
| `otp export [filtro]` | Mostrar QR de migración para Google Authenticator (pide confirmación) |

KRunner muestra como mucho 15 resultados: si hay más coincidencias, aparece «+N más» y basta
con escribir más letras. La palabra clave es configurable; `otpr` se acepta como alias.

### CLI

```
otprunner list [filtro]
otprunner code <nombre> [--copy]
otprunner add [nombre] --screen | --camera | --clipboard | --uri URI
otprunner import <fichero|URI>
otprunner export [filtro] [--format migration|otpauth] [--qr]
otprunner remove <nombre>        (alias: rm)
otprunner rename <viejo> <nuevo>
otprunner install | uninstall | doctor
```

## Instalación

```bash
pipx install .        # o: uv tool install .
otprunner install     # registra el runner en KRunner, la unidad systemd de usuario y el icono
otprunner doctor      # comprueba keystore, portapapeles, captura, etc.
```

`otprunner uninstall` deshace lo anterior. Los secretos permanecen en el keystore.

### Dependencias del sistema (opcionales, según escritorio)

- Captura de pantalla: portal XDG (normalmente ya presente), o `spectacle` / `gnome-screenshot` / `maim`.
- Portapapeles: Klipper (KDE), o `wl-clipboard` (Wayland) / `xclip` (X11).
- Confirmaciones: `kdialog` o `zenity`.
- Cámara: `zbar-tools` (`zbarcam`), o bien `pipx inject otprunner opencv-python`.
  Con una exportación de Google en varios QR, la cámara sigue abierta hasta leerlos todos.

## Configuración

Opcional, en `~/.config/otprunner/config.toml` (tras cambiar `keywords`, repite `otprunner install`):

```toml
backend = "auto"            # auto (KWallet si existe, si no Secret Service) | kwallet | secretservice
keywords = ["otp", "otpr"]  # palabras clave en KRunner
idle_timeout = 600          # segundos sin uso antes de cerrar el servicio (0 = nunca)
show_codes = "selected"     # selected | always | never
camera = "/dev/video0"      # opcional: dispositivo de la cámara
language = "es"             # opcional: idioma de la interfaz (por defecto, el del escritorio)
```

`show_codes`:
- `selected` (por defecto): el código va en el subtítulo, que KRunner (Plasma 5) solo muestra
  en la línea seleccionada; así no se ven todos a la vez.
- `always`: código en el título, siempre visible, con su hora de caducidad y el siguiente.
- `never`: no se muestra; Enter lo copia.

KRunner no refresca los resultados hasta que cambia la búsqueda; Enter copia siempre el código vigente.

## Cómo funciona

- KRunner habla con el runner por DBus (`org.kde.krunner1`). El servicio se activa por DBus,
  que delega en una unidad systemd de usuario: logs en `journalctl --user -u otprunner`.
- El servicio cachea las cuentas durante la sesión de KRunner y se cierra tras
  `idle_timeout` segundos sin uso: los secretos no se quedan en memoria indefinidamente.
- Cada cuenta guarda la URI `otpauth://` completa. En KWallet, como una entrada de la
  carpeta `otprunner` del monedero; en Secret Service, como un item con atributos
  `application=otprunner` y `account=<nombre>`.
- Las imágenes con secretos (capturas, QR de export) se crean en `$XDG_RUNTIME_DIR/otprunner`
  (en memoria, permisos 0700) y se borran siempre.

## Icono

<img src="src/otprunner/data/otprunner.svg" width="64" alt="icono de OTPRunner">

- **Qué representa**: un anillo de cuenta atrás alrededor de una bocallave. Junta los dos
  elementos de un TOTP: un secreto que solo tú tienes y un código que caduca. El tramo
  abierto del anillo es el tiempo ya consumido de los 30 s.
- **Por qué no un candado o un escudo**: son los iconos genéricos de gestor de contraseñas;
  OTPRunner no guarda contraseñas, da códigos efímeros.
- **Estilo**: plano, en el azul de Breeze (`#3daee9`) con un degradado suave, y una retícula
  de 128 px con márgenes de 8 px, como los iconos de aplicación de Plasma. Solo blanco sobre
  azul: contrasta igual en temas claros y oscuros.
- **Tamaños pequeños**: a 16 y 22 px (KRunner, bandeja, notificaciones) se usa una versión
  dibujada sobre una retícula de 16 px: anillo más grueso, sin pista de fondo y bocallave
  más grande, para que no se empaste.
- **Nombre**: *OTPRunner* en lo visible (KRunner, notificaciones, diálogos); `otprunner`
  en lo técnico (comando, paquete, ficheros, DBus), que se escribe en minúsculas.
- **Dónde se usa**: plugin y resultados de KRunner, y notificaciones. Las acciones (añadir,
  borrar, exportar…) conservan los iconos estándar del tema, que ya dicen qué hacen.

## Desarrollo

```bash
uv venv && uv pip install -e '.[dev]'
pytest
```

Traducciones (gettext; el inglés es el idioma fuente, catálogos en `src/otprunner/locale/`):

```bash
scripts/i18n.sh update     # tras cambiar textos: extrae y actualiza los .po
scripts/i18n.sh init fr    # idioma nuevo
scripts/i18n.sh compile    # genera los .mo (van en el paquete)
```

Los tests fallan si queda alguna cadena sin traducir o un `.mo` desactualizado.

Para depurar el runner: `systemctl --user stop otprunner` y lanzar `otprunner serve -v`
en una terminal; KRunner hablará con ese proceso.

Referencias recopiladas: [docs/referencias.md](docs/referencias.md).
Proyectos similares y plan de publicación: [docs/publicacion.md](docs/publicacion.md).

## Hoja de ruta

- Publicación: PyPI → KDE Store → Flathub (ver [docs/publicacion.md](docs/publicacion.md)).
- (Opcional) Integración con la búsqueda de GNOME Shell.
