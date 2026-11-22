# Publicación y proyectos similares

Notas de 2026-11. Revisar enlaces y versiones antes de actuar.

## Proyectos similares

Ninguno encontrado que haga lo mismo (TOTP con semillas normales, en el keystore del
sistema, desde KRunner):

| Proyecto | Qué hace | Diferencia |
|---|---|---|
| [yubikey-oath-krunner](https://github-users.yhajoa.workers.dev/jkolo/yubikey-oath-krunner) | Runner Plasma 6: lista cuentas OATH y copia el código | Secretos en una YubiKey |
| [yubioath-krunner](https://aur.archlinux.org/packages/yubioath-krunner) | Runner antiguo para YubiKey OATH | Ídem |
| [krunner-pass](https://github.com/akermu/krunner-pass) | Runner para `pass`, con pass-otp | Requiere `pass` + GPG |
| Runner de KeePassXC | Copia contraseñas; TOTP como acción secundaria | Requiere KeePassXC |
| OTPClient, Keysmith, GNOME Authenticator | Apps de escritorio con ventana propia | No integran con el lanzador |

## Cómo aparece una app al buscar en KRunner

Las sugerencias de apps no instaladas (p. ej. OTPClient al escribir «otp») vienen del
runner **«Software Center»** de plasma-workspace, que consulta los metadatos **AppStream**
de los repositorios que conoce Discover
([código](https://lxr.kde.org/source/plasma/plasma-workspace/runners/appstream/appstreamrunner.cpp)).
Para salir ahí hay que estar en un repositorio que publique AppStream (Flathub, archivo de
la distro). Un PPA no publica AppStream.

## Plan de publicación

0. **Requisitos previos**: elegir licencia (la versión antigua decía LGPL), repositorio
   público, `metainfo.xml` de AppStream, icono propio, capturas, CHANGELOG, CI con tests.
1. **PyPI**: `pipx install otprunner && otprunner install`. Base del resto.
2. **KDE Store, categoría «KRunner plugins»**: aparece en *Configuración de KRunner →
   Obtener nuevos complementos* (KNewStuff). El paquete lleva un `install.sh` que hace
   `pipx install` + `otprunner install` y un `uninstall.sh`. Esfuerzo bajo; es el canal
   habitual de los runners.
3. **Flathub** (opcional): lo haría aparecer en Discover y en «Software Center».
   - Flatpak permite exportar `share/krunner/dbusplugins`
     ([KDE bug 493859](https://bugs.kde.org/show_bug.cgi?id=493859), flatpak PR #5938):
     comprobar la versión mínima de flatpak.
   - Permisos: `--talk-name=org.freedesktop.secrets`, `org.kde.kwalletd5/6`,
     `org.kde.klipper`, `org.kde.krunner`, notificaciones; portal Screenshot (spectacle no
     está en el sandbox); `--device=all` para la cámara (o solo OpenCV dentro).
   - `otprunner install` no aplica: los ficheros los exporta flatpak.
4. **Distribuciones** (AUR, Debian/Ubuntu): AUR es sencillo; Debian/Ubuntu requiere
   mantenedor y plazos largos.
