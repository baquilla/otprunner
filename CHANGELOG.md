# Changelog

## 0.2.0 (unreleased)

First public release, rewritten from a personal script.

- Secrets in the system keystore: native KWallet on KDE, Secret Service elsewhere.
- KRunner: `otp` lists the commands; filters show matching accounts and the commands that
  start with the text; long lists are trimmed so the commands stay visible.
- Codes shown only on the selected line by default (`show_codes`).
- Add accounts from KRunner or the CLI: QR code on screen, clipboard (link or image), camera.
- Import and export `otpauth://` and Google Authenticator `otpauth-migration://`; a single
  account exports as `otpauth://`; several, as transfer codes shown together in one window.
- Links stored exactly as received; same secret replaces the link and keeps the name.
- CLI with the same commands as the runner; `doctor` diagnostics.
- DBus activation through a systemd user unit; idle exit.
- English and Spanish interface.
- Icon.
