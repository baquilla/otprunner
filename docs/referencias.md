# Referencias

Recopiladas durante la primera versión.

## KRunner

- Interfaz DBus de runners: https://invent.kde.org/frameworks/krunner/-/blob/master/src/data/org.kde.krunner1.xml
- Implementación del lado de KRunner: https://invent.kde.org/frameworks/krunner/-/blob/master/src/dbusrunner.cpp
- Plantilla Python + DBus: https://store.kde.org/p/1333634 (simple_krunner_python_template)
- Tutorial antiguo (Plasma 4): https://techbase.kde.org/Development/Tutorials/Plasma4/AbstractRunner
- https://github.com/matsjoyce/python-krunner
- https://sigoa.github.io/krunner-bridge/

## Keystore

- Secret Service API: https://specifications.freedesktop.org/secret-service-spec/latest/
- KWallet: https://techbase.kde.org/Development/Tutorials/KWallet ·
  https://wiki.archlinux.org/title/KDE_Wallet
- `keyring` (Python): https://pypi.org/project/keyring/ — no permite enumerar items,
  por eso usamos Secret Service directamente.

## TOTP / QR

- RFC 6238 (TOTP), formato `otpauth://`: https://github.com/google/google-authenticator/wiki/Key-Uri-Format
- `otpauth-migration://`: protobuf `MigrationPayload` de Google Authenticator.

## Otros

- Registrar un manejador de URL XDG: https://unix.stackexchange.com/questions/497146/create-a-custom-url-protocol-handler
