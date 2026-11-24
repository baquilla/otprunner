#!/bin/sh
# OTPRunner entry in the KDE Store (Plasma 5).
#
# The entry installed nothing, so there is nothing to remove here. This script shows how to
# remove OTPRunner itself, and leaves a shell open to do it.
set -u

case "${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
es*) es=1 ;;
*) es= ;;
esac

say() { if [ -n "$es" ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }

export PATH="$HOME/.local/bin:$PATH"

echo
say "This KDE Store entry installed nothing, so there is nothing else to remove." \
    "Esta entrada de la KDE Store no instaló nada, así que no hay nada más que quitar."
echo
if command -v otprunner >/dev/null 2>&1; then
    say "To remove OTPRunner itself:" "Para quitar OTPRunner:"
    echo
    echo "  otprunner uninstall"
    echo "  pipx uninstall otprunner"
    echo
    say "Your secrets stay in the keystore." "Tus secretos se quedan en el keystore."
else
    say "OTPRunner is not installed." "OTPRunner no está instalado."
fi
echo

if [ -t 0 ] && [ -t 1 ] && command -v otprunner >/dev/null 2>&1; then
    say "A shell is open below; close this window when you are done." \
        "Abajo tienes una consola; cierra esta ventana cuando acabes."
    echo
    cd "$HOME" || exit 0
    exec "${SHELL:-/bin/sh}" -i
fi
