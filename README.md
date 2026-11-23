# OTPRunner

**English** · [Español](README.es.md)

TOTP codes in your desktop launcher (KRunner on KDE Plasma), with the secrets kept in the
system keystore and an equivalent command line.

> Status: pre-release (0.2.0.dev0).

## Features

- Search and copy TOTP codes from KRunner (`otp <filter>`) or from the terminal.
- Secrets live in whatever system keystore is available: on KDE, KWallet (an `otprunner`
  folder in your wallet); elsewhere, the Secret Service (GNOME Keyring, KeePassXC).
  Never in plain files.
- Add accounts without opening a terminal: capture an area of the screen with the QR code,
  paste from the clipboard, or show it to the camera.
- Import and export as `otpauth://` and `otpauth-migration://` (Google Authenticator),
  including export as QR codes to move accounts to your phone.
- English and Spanish interface: follows the desktop language (or `language` in the config).
- Works on Plasma 5.27 and 6, X11 and Wayland, using whichever tool is available
  (XDG portal, spectacle, Klipper, wl-copy, xclip…). `otprunner doctor` shows what it uses
  and what is missing.

## Usage

### KRunner

| You type | You get |
|---|---|
| `otp` | A search hint and the available commands (no codes) |
| `otp <filter>` | Accounts containing the text (Enter copies the code) and, at the end, the commands starting with it: `otp re` → rename, remove |
| `otp add [name]` | Add from a screen capture · the clipboard · the camera |
| `otp rename [filter]` | Rename (asks for the new name) |
| `otp remove [filter]` | Remove (asks for confirmation); `rm` works too |
| `otp export [filter]` | Show migration QR codes for Google Authenticator (asks for confirmation) |

KRunner shows at most 15 results: when there are more matches, a “+N more” line appears;
just type a few more letters. The keyword is configurable; `otpr` is accepted as an alias.

### Command line

```
otprunner list [filter]
otprunner code <name> [--copy]
otprunner add [name] --screen | --camera | --clipboard | --uri URI
otprunner import <file|URI>
otprunner export [filter] [--format migration|otpauth] [--qr]
otprunner remove <name>          (alias: rm)
otprunner rename <old> <new>
otprunner install | uninstall | doctor
```

## Installation

```bash
pipx install .        # or: uv tool install .
otprunner install     # registers the KRunner plugin, the systemd user unit and the icon
otprunner doctor      # checks keystore, clipboard, screen capture, etc.
```

`otprunner uninstall` undoes it. The secrets stay in the keystore.

### System dependencies (optional, depending on the desktop)

- Screen capture: XDG portal (usually present), or `spectacle` / `gnome-screenshot` / `maim`.
- Clipboard: Klipper (KDE), or `wl-clipboard` (Wayland) / `xclip` (X11).
- Confirmation dialogs: `kdialog` or `zenity`.
- Camera: `zbar-tools` (`zbarcam`), or `pipx inject otprunner opencv-python`.
  With a Google export split into several QR codes, the camera stays open until it has read them all.

## Configuration

Optional, in `~/.config/otprunner/config.toml` (after changing `keywords`, run `otprunner install` again):

```toml
backend = "auto"            # auto (KWallet if present, otherwise Secret Service) | kwallet | secretservice
keywords = ["otp", "otpr"]  # KRunner keywords
idle_timeout = 600          # idle seconds before the service exits (0 = never)
show_codes = "selected"     # selected | always | never
camera = "/dev/video0"      # optional: camera device
language = "es"             # optional: interface language (default: the desktop's)
```

`show_codes`:
- `selected` (default): the code goes in the subtitle, which KRunner (Plasma 5) only shows on
  the selected line, so they are not all visible at once.
- `always`: the code in the title, always visible, with its expiry time and the next code.
- `never`: not shown; Enter copies it.

KRunner does not refresh results until the query changes; Enter always copies the current code.

## How it works

- KRunner talks to the runner over DBus (`org.kde.krunner1`). The service is DBus-activated
  through a systemd user unit: logs in `journalctl --user -u otprunner`.
- The service caches the accounts during the KRunner session and exits after `idle_timeout`
  idle seconds, so the secrets do not stay in memory indefinitely.
- Each account stores the full `otpauth://` URI. In KWallet, as an entry in the wallet's
  `otprunner` folder; in the Secret Service, as an item with the attributes
  `application=otprunner` and `account=<name>`.
- Images containing secrets (captures, export QR codes) are written to
  `$XDG_RUNTIME_DIR/otprunner` (in memory, mode 0700) and always deleted.

## Icon

<img src="src/otprunner/data/otprunner.svg" width="64" alt="OTPRunner icon">

- **What it shows**: a countdown ring around a keyhole — the two parts of a TOTP: a secret
  only you hold and a code that expires. The open stretch of the ring is the part of the
  30 s already gone.
- **Why not a padlock or a shield**: those are the generic password-manager icons;
  OTPRunner does not store passwords, it hands out short-lived codes.
- **Style**: flat, in Breeze blue (`#3daee9`) with a soft gradient, on a 128 px grid with
  8 px margins like Plasma application icons. White on blue only, so it reads the same on
  light and dark themes.
- **Small sizes**: at 16 and 22 px (KRunner, tray, notifications) a version drawn on a 16 px
  grid is used: thicker ring, no background track and a larger keyhole, so it stays crisp.
- **Name**: *OTPRunner* wherever it is visible (KRunner, notifications, dialogs); `otprunner`,
  lowercase, for technical identifiers (command, package, files, DBus).
- **Where it is used**: the KRunner plugin and results, and notifications. Actions (add,
  remove, export…) keep the theme's standard icons, which already say what they do.

## Development

```bash
uv venv && uv pip install -e '.[dev]'
pytest
```

Translations (gettext; English is the source language, catalogs in `src/otprunner/locale/`):

```bash
scripts/i18n.sh update     # after changing strings: extract and update the .po files
scripts/i18n.sh init fr    # new language
scripts/i18n.sh compile    # build the .mo files (shipped in the package)
```

Tests fail if a string is left untranslated or a `.mo` file is out of date.

To debug the runner: `systemctl --user stop otprunner` and run `otprunner serve -v` in a
terminal; KRunner will talk to that process.

Background notes (in Spanish): [references](docs/referencias.md),
[similar projects and publishing plan](docs/publicacion.md).

## Roadmap

- Publishing: PyPI → KDE Store → Flathub (see [docs/publicacion.md](docs/publicacion.md)).
- (Optional) GNOME Shell search integration.
