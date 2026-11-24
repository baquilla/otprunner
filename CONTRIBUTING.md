# Contributing

Bug reports, translations and pull requests are welcome. If you fork OTPRunner to change
something, consider sending the change back here so everyone gets it.

## Development

```bash
git clone https://github.com/baquilla/otprunner && cd otprunner
uv venv && uv pip install -e '.[dev]'     # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'
pytest
```

To try your working copy in KRunner, install it in editable mode and register it:

```bash
pipx install -e . --force
otprunner install
```

To watch the runner while you use KRunner: `systemctl --user stop otprunner` and run
`otprunner serve -v` in a terminal. `otprunner serve --demo` does the same with made-up
accounts, which is handy for screenshots.

## Layout

| Module | Role |
|---|---|
| `runner.py` | KRunner DBus service: matches and actions |
| `cli.py` | Command line |
| `otpauth.py`, `migration.py` | `otpauth://` accounts and codes; Google `otpauth-migration://` codec |
| `importer.py`, `adding.py` | Parsing links, adding and updating accounts |
| `store/` | Keystore backends (KWallet, Secret Service, in-memory for tests) |
| `capture.py`, `camera.py`, `clipboard.py`, `dialogs.py`, `notify.py` | Desktop integration, each trying the available tools in order |
| `install.py`, `doctor.py` | Installation and diagnostics |

## Translations

gettext, with English as the source language; catalogs are in `src/otprunner/locale/`.

```bash
scripts/i18n.sh update     # after changing strings: extract and update the .po files
scripts/i18n.sh init fr    # start a new language
scripts/i18n.sh compile    # build the .mo files (they are shipped in the package)
```

The tests fail if a string is left untranslated or a `.mo` file is out of date.

## Guidelines

- Never log, print or commit secrets. Test data uses made-up secrets.
- Visible text says *OTPRunner* (use `APP_NAME`); technical identifiers stay `otprunner`.
- Prefer small, focused changes, each with its test.
