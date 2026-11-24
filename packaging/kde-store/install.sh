#!/bin/sh
# OTPRunner entry in the KDE Store (Plasma 5).
#
# This script installs nothing. KRunner's "Get New Plugins" runs it in a terminal; it checks
# what is already there and shows the commands to install OTPRunner with pipx, then leaves a
# shell open so the user can run them. Source: https://github.com/baquilla/otprunner
set -u

case "${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
es*) es=1 ;;
*) es= ;;
esac

# say "English" "Español"
say() { if [ -n "$es" ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
check() { if [ "$1" -eq 0 ]; then printf '  ✓ %s\n' "$2"; else printf '  ✗ %s\n' "$2"; fi; }

export PATH="$HOME/.local/bin:$PATH" # where pipx puts its commands

python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null
has_python=$?
command -v pipx >/dev/null 2>&1
has_pipx=$?
command -v otprunner >/dev/null 2>&1
has_otprunner=$?
test -f "${XDG_DATA_HOME:-$HOME/.local/share}/krunner/dbusplugins/otprunner.desktop"
registered=$?

echo
say "OTPRunner: TOTP codes in KRunner" "OTPRunner: códigos TOTP en KRunner"
echo
say "This KDE Store entry does not install anything. OTPRunner is installed from PyPI" \
    "Esta entrada de la KDE Store no instala nada. OTPRunner se instala desde PyPI"
say "with pipx, by running the commands below yourself." \
    "con pipx, ejecutando tú mismo los comandos de abajo."
echo
check $has_python "Python ≥ 3.10"
check $has_pipx "pipx"
check $has_otprunner "OTPRunner"
check $registered "$(say "KRunner plugin registered" "complemento de KRunner registrado")"
echo

if [ $has_otprunner -eq 0 ] && [ $registered -eq 0 ]; then
    say "OTPRunner is already installed. To update it:" "OTPRunner ya está instalado. Para actualizarlo:"
    echo
    echo "  pipx upgrade otprunner"
else
    say "To install it:" "Para instalarlo:"
    echo
    if [ $has_python -ne 0 ] || [ $has_pipx -ne 0 ]; then
        echo "  sudo apt install python3 pipx    # Debian, Ubuntu, Kubuntu"
        echo "  sudo dnf install pipx            # Fedora"
        echo "  sudo zypper install python3-pipx # openSUSE"
        echo "  sudo pacman -S python-pipx       # Arch"
    fi
    [ $has_otprunner -eq 0 ] || echo "  pipx install OTPRunner"
    echo "  otprunner install"
    echo
    say "Then open KRunner and type: otp add" "Después abre KRunner y escribe: otp add"
fi
echo
say "More information: https://github.com/baquilla/otprunner" \
    "Más información: https://github.com/baquilla/otprunner"
echo

if [ -t 0 ] && [ -t 1 ]; then
    say "A shell is open below to run them; close this window when you are done." \
        "Abajo tienes una consola para ejecutarlos; cierra esta ventana cuando acabes."
    echo
    cd "$HOME" || exit 0
    exec "${SHELL:-/bin/sh}" -i
fi
