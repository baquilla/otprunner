# Design

## How it works

```
KRunner ──DBus (org.kde.krunner1)──▶ otprunner serve ──▶ KWallet / Secret Service
                                         │
                                         ├─▶ clipboard (Klipper, wl-copy, xclip…)
                                         └─▶ notifications, dialogs, screen capture, camera
```

- `otprunner install` writes three small files: the KRunner plugin description
  (`~/.local/share/krunner/dbusplugins/`), a DBus service file and a systemd user unit.
  The service is DBus-activated: it starts on the first KRunner query and its logs go to
  `journalctl --user -u otprunner`.
- KRunner calls `Match` on every keystroke after the keyword. The service answers from an
  in-memory copy of the accounts, read from the keystore once per KRunner session.
- After `idle_timeout` seconds without queries (10 minutes by default) the service exits, so
  the secrets do not stay in memory; DBus starts it again on the next query.
- Long actions (copying, capturing, dialogs) run in the background so KRunner never waits.

## Accounts and names

Each account is one `otpauth://` link, stored **exactly as it arrived**. The only change
OTPRunner ever makes to it is the `counter` of HOTP accounts, which goes up each time a code
is used.

The account's name is its key in the keystore and what you search for. It is computed once,
when the account is added:

1. Take the label of the link (between `otpauth://totp/` and `?`) as is. It is never
   split at “:” and nothing is trimmed off it.
2. If the link has an `issuer` and the label does not already start with `issuer:`, put
   `issuer:` in front.

| Link | Name |
|---|---|
| `otpauth://totp/alice?…` | `alice` |
| `otpauth://totp/GitHub:alice?…` | `GitHub:alice` |
| `otpauth://totp/alice?…&issuer=GitHub` | `GitHub:alice` |
| `otpauth://totp/GitHub:alice?…&issuer=GitHub` | `GitHub:alice` |
| `otpauth://totp/x:y?…&issuer=GitHub` | `GitHub:x:y` |

Control characters (some exporters leave line breaks) are dropped from the name, not from
the stored link. You can rename an account at any time; the link is not touched.

**Same secret, new link.** Adding a code whose secret is already stored replaces the stored
link with the new one and keeps the existing name. Adding the identical link again does nothing.

**Name clashes.** If the name is taken by a different secret, the new account gets a
“ (2)” suffix.

**Google Authenticator transfers** (`otpauth-migration://`) carry name, issuer and
parameters instead of links; OTPRunner builds a standard link from them. When exporting,
it writes the format current versions of Google Authenticator accept (payload `version` 2,
no `batch_id`); the app silently ignores codes with `version` 1. `scripts/migration-dump.py`
prints the structure of a transfer link, without secrets, to compare formats.

## Storage

| Backend | Where | Chosen when |
|---|---|---|
| KWallet (native) | One password entry per account in an `otprunner` folder of the network wallet | `kwalletd6` or `kwalletd5` is running |
| Secret Service | One item per account, attributes `application=otprunner`, `account=<name>` | otherwise (GNOME Keyring, KeePassXC…) |

The native KWallet API is preferred on KDE: its Secret Service bridge puts every item in a
shared “Secret Service” folder and treats “/” in labels as a folder separator.

## Security notes

- Secrets are only ever in the keystore and, briefly, in the service's memory.
- Codes are hidden by default: only the selected line shows one (`show_codes = "selected"`).
- Screen captures and export QR images are written to `$XDG_RUNTIME_DIR/otprunner` (a
  RAM-backed directory, mode 0700, files 0600) and deleted right after use.
- Exporting always asks first and warns that anyone who sees the screen can copy the accounts.
- Klipper keeps a clipboard history; copied codes expire within a minute, but they remain in
  that history until it is cleared.
- `otprunner serve --demo` serves made-up accounts with random secrets, for screenshots and
  demonstrations.

## Translations

gettext, with English as the source language. The language follows the desktop
(`LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`) unless `language` is set in the configuration.
The first language in the list that is English or has a catalog wins, so
`LANGUAGE=en_US:es` gives English rather than falling through to Spanish.

## Icon

<img src="../src/otprunner/data/otprunner.svg" width="64" alt="OTPRunner icon">

- **What it shows**: a countdown ring around a keyhole: the two parts of a TOTP, a secret
  only you hold and a code that expires. The open stretch of the ring is the part of the
  30 s already gone.
- **Why not a padlock or a shield**: those are the generic password-manager icons;
  OTPRunner does not store passwords, it hands out short-lived codes.
- **Style**: flat, in Breeze blue (`#3daee9`) with a soft gradient, on a 128 px grid with
  8 px margins like Plasma application icons. White on blue only, so it reads the same on
  light and dark themes.
- **Small sizes**: at 16 and 22 px (KRunner, tray, notifications) a version drawn on a
  16 px grid is used: thicker ring, no background track and a larger keyhole.
- **Name**: *OTPRunner* wherever it is visible; `otprunner`, lowercase, for technical
  identifiers (command, package, files, DBus).
- **Where it is used**: the KRunner plugin and results, and notifications. Actions (add,
  remove, export…) keep the theme's standard icons, which already say what they do.

## Related projects

| Project | Difference |
|---|---|
| yubikey-oath-krunner | Codes from a YubiKey |
| [ente-auth-krunner](https://github.com/Bricks666/ente-auth-krunner) | Reads the codes of the Ente Auth desktop app (Plasma 6, TOTP only) |
| [krunner-pass](https://github.com/akermu/krunner-pass) | Needs `pass` and GPG (TOTP through pass-otp) |
| KeePassXC's KRunner integration | Needs KeePassXC; TOTP is a secondary action |
| OTPClient, Keysmith, GNOME Authenticator | Desktop apps with their own window |

## References

- KRunner DBus runner interface: [org.kde.krunner1.xml](https://invent.kde.org/frameworks/krunner/-/blob/master/src/data/org.kde.krunner1.xml)
- [Secret Service API](https://specifications.freedesktop.org/secret-service-spec/latest/)
- [RFC 4226 (HOTP)](https://www.rfc-editor.org/rfc/rfc4226), [RFC 6238 (TOTP)](https://www.rfc-editor.org/rfc/rfc6238),
  [Key URI format](https://github.com/google/google-authenticator/wiki/Key-Uri-Format)
