# Contributing

Bug reports, translations and pull requests are welcome. If you fork OTPRunner to change
something, consider sending the change back here so everyone gets it.

## Development

```bash
git clone https://github.com/baquilla/otprunner && cd otprunner
uv venv && uv pip install -e '.[dev]'     # or: python -m venv .venv && .venv/bin/pip install -e '.[dev]'
pre-commit install --hook-type pre-commit --hook-type commit-msg
pytest
```

The hooks run `ruff check --fix`, `ruff format` and the commit message check on every commit;
CI runs the same checks plus the tests on Python 3.10 to 3.14.

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

## Code style

- [Ruff](https://docs.astral.sh/ruff/) for linting and formatting (configuration in
  `pyproject.toml`, 120 columns). `ruff check --fix && ruff format` before committing, or let
  the pre-commit hook do it.
- New code, comments and docstrings in English. (Older modules still have Spanish comments;
  they are being translated.)
- User-visible strings go through `_()` (or `ngettext()` / `N_()`), in English.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), in English, imperative mood,
summary up to 100 characters:

```
<type>(<scope>): <summary>

feat(runner): offer YubiKey codes next to keystore accounts
fix(export): keep the QR window inside short screens
docs: describe the YubiKey backend in the roadmap
```

- **Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
  `chore`, `revert`. Add `!` after the type/scope for breaking changes.
- **Scopes** (optional): `runner`, `cli`, `store`, `kwallet`, `secretservice`, `capture`,
  `camera`, `clipboard`, `export`, `import`, `install`, `doctor`, `i18n`.
- One logical change per commit: keep reformatting apart from behaviour changes.
- `scripts/check-commits.py` checks messages (commit-msg hook, and CI for pushes and pull requests).

## Pull requests

- Branch from `main`, keep the change focused and add or update its tests.
- `pytest`, `ruff check` and `ruff format --check` must pass.
- Update `CHANGELOG.md` (under a new “Unreleased” heading) and the docs when behaviour changes.

## Releasing

1. Set `__version__` in `src/otprunner/__init__.py` and date the `CHANGELOG.md` entry.
2. Commit (`chore: release X.Y.Z`), tag `vX.Y.Z` and push the tag.
3. The release workflow tests, builds, publishes to PyPI (Trusted Publishing) and creates
   the GitHub release.

### KDE Store

The KDE Store entry is only a showcase: its archive installs nothing and does not depend on
the version, so it only needs uploading again when `packaging/kde-store/` changes.

- `scripts/kde-store.sh` builds `build/kde-store/otprunner-kde-store.tar.gz`.
- `packaging/kde-store/README` is also the entry's description on the store.
- On *Install*, KRunner's plugin installer asks for confirmation (with buttons to view the
  README and the script) and runs `install.sh` in a terminal: it checks Python, pipx and
  OTPRunner, prints the commands and leaves a shell open. `uninstall.sh` does the same
  for removal.

## Guidelines

- Never log, print or commit secrets. Test data uses made-up secrets.
- Visible text says *OTPRunner* (use `APP_NAME`); technical identifiers stay `otprunner`.
