# Usage

## KRunner

| You type | You get |
|---|---|
| `otp` | A search hint and the available commands (no codes) |
| `otp <filter>` | Accounts whose name contains the text (<kbd>Enter</kbd> copies the code) and, at the end, the commands starting with it: `otp re` → rename, remove |
| `otp add [name]` | Add from a QR code on screen · the clipboard · the camera |
| `otp rename [filter]` | Rename (asks for the new name) |
| `otp remove [filter]` | Remove (asks for confirmation); `rm` works too |
| `otp export [filter]` | Show QR codes to move accounts to the phone (asks for confirmation) |

- The keyword is configurable; `otpr` is accepted as an alias.
- Choosing a command reopens KRunner with it typed (`otp add `), so you can add a name or filter.
- KRunner shows at most 15 results, shared among all the runners that answer (with two
  of them, about 7 each). OTPRunner returns at most `max_results` (7) and keeps the commands
  and a “+N more” line visible; type more letters to narrow the list down.
- KRunner does not refresh results while the text stays the same, so a code on screen may
  have expired. <kbd>Enter</kbd> always copies the current code.

### Adding accounts

- **From the screen**: select the area with the QR code (spectacle, the XDG portal,
  `gnome-screenshot` or `maim`, whichever is available).
- **From the clipboard**: an `otpauth://` or `otpauth-migration://` link, or an image of a QR code.
- **With the camera**: hold the QR code in front of the webcam. With a Google Authenticator
  export split into several QR codes, the camera stays open until it has read them all.

If a code with the same secret is already stored, its link is replaced by the new one and
the account keeps its name. See [Design](design.md#accounts-and-names).

### Exporting

- **A single account** is shown as its own `otpauth://` QR code, which any authenticator app reads.
- **Several accounts** are shown as Google Authenticator transfer codes, all in one window
  (10 accounts per code). In Google Authenticator: *Transfer accounts → Import accounts*.
  Google's format only supports 6 or 8 digits and a 30 s period; other accounts are skipped
  with a notice (export them one by one).

## Command line

```
otprunner list [filter]
otprunner code <name> [--copy]
otprunner add [name] --screen | --camera | --clipboard | --uri URI
otprunner import <file|URI>
otprunner export [filter] [--format auto|migration|otpauth] [--batch N] [--qr]
otprunner remove <name> [-y]       (alias: rm)
otprunner rename <old> <new>
otprunner install | uninstall | doctor
otprunner serve [-v] [--idle SECONDS] [--demo]
```

`<name>` can be the full name or any unique part of it. `export --format auto` (the
default) writes `otpauth://` for one account and `otpauth-migration://` for several; with
`--qr` the codes are drawn in the terminal.

## Configuration

Optional, in `~/.config/otprunner/config.toml`. After changing `keywords`, run
`otprunner install` again; for the rest, `systemctl --user restart otprunner`.

```toml
backend = "auto"            # auto (KWallet if present, otherwise Secret Service) | kwallet | secretservice
keywords = ["otp", "otpr"]  # KRunner keywords
idle_timeout = 600          # idle seconds before the service exits (0 = never)
show_codes = "selected"     # selected | always | never
max_results = 7             # results OTPRunner returns (raise it if no other runner answers)
camera = "/dev/video0"      # optional: camera device
language = "es"             # optional: interface language (default: the desktop's)
```

`show_codes`:
- `selected` (default): the code goes in the subtitle, which KRunner (Plasma 5) only shows
  on the selected line, so they are not all visible at once.
- `always`: the code in the title, always visible, with its expiry time and the next code.
- `never`: not shown; <kbd>Enter</kbd> copies it.

## System tools

OTPRunner uses whatever the desktop provides; `otprunner doctor` shows what it found and
what is missing.

| For | Any of |
|---|---|
| Keystore | KWallet (`kwalletd5`/`kwalletd6`) · Secret Service (GNOME Keyring, KeePassXC…) |
| Screen capture | `spectacle` · XDG desktop portal · `gnome-screenshot` · `maim` |
| Clipboard | Klipper · `wl-clipboard` (Wayland) · `xclip` / `xsel` (X11) |
| Dialogs | `kdialog` · `zenity` |
| Camera (optional) | `zbar-tools` (`zbarcam`) · `pipx inject otprunner opencv-python` |

## Troubleshooting

- `otprunner doctor` checks the keystore, the installation and the tools above.
- Logs: `journalctl --user -u otprunner`.
- To watch the runner live: `systemctl --user stop otprunner`, then `otprunner serve -v` in a
  terminal; KRunner talks to that process.
- Nothing appears in KRunner after installing: `kquitapp5 krunner` (or `kquitapp6`) and try again.
