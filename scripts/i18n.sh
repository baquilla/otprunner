#!/bin/sh
# Mantenimiento de traducciones (requiere: pip install -e '.[dev]').
#   scripts/i18n.sh update    extrae las cadenas y actualiza los .po
#   scripts/i18n.sh compile   compila los .mo que van en el paquete
#   scripts/i18n.sh init XX   crea el catálogo de un idioma nuevo
set -eu
cd "$(dirname "$0")/.."
LOCALE=src/otprunner/locale
POT=$LOCALE/otprunner.pot
case "${1:-}" in
  update)
    pybabel extract -o "$POT" --project=OTPRunner --copyright-holder="OTPRunner contributors" \
      --no-location --sort-output -k _ -k N_ -k ngettext:1,2 src/otprunner
    pybabel update -i "$POT" -d "$LOCALE" -D otprunner --no-fuzzy-matching ;;
  compile)
    pybabel compile -d "$LOCALE" -D otprunner --statistics ;;
  init)
    pybabel init -i "$POT" -d "$LOCALE" -D otprunner -l "$2" ;;
  *)
    echo "uso: $0 update | compile | init <idioma>" >&2; exit 2 ;;
esac
