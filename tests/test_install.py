import re

from otprunner import config, install


def test_match_regex():
    rx = install.match_regex(["otp", "otpr"])
    py = re.compile(rx.replace("(?i)", ""), re.IGNORECASE)
    assert py.match("otp") and py.match("OTPR git") and not py.match("otpx") and not py.match("hola otp")
    assert install.match_regex(["o.t"]) is None


def test_generated_files(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    desktop = install.runner_desktop(config.Config())
    assert "X-Plasma-API=DBus" in desktop and "X-Plasma-API-Minimum-Version=2.0" in desktop
    assert "\\s" not in desktop  # en .desktop «\s» significa espacio
    svc = install.dbus_service(systemd=True)
    assert "SystemdService=otprunner.service" in svc and " -m otprunner serve" in svc
    assert "SystemdService" not in install.dbus_service(systemd=False)
    assert "Type=dbus" in install.systemd_unit()
    p = install.paths()
    assert str(p["runner"]).endswith("data/krunner/dbusplugins/otprunner.desktop")


def test_install_icons(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    out = install.install_icons()
    assert [p.relative_to(tmp_path).as_posix() for p in out] == [
        "icons/hicolor/scalable/apps/otprunner.svg",
        "icons/hicolor/16x16/apps/otprunner.svg",
        "icons/hicolor/22x22/apps/otprunner.svg",
    ]
    assert all(p.read_text().startswith("<svg") for p in out)
    assert "Icon=otprunner" in install.runner_desktop(config.Config())
    assert all(p in install.paths().values() for p in out)


def test_install_replaces_old_dbus_name(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(install, "has_systemd_user", lambda: False)
    monkeypatch.setattr(install, "_run", lambda cmd: None)
    old = tmp_path / "data/dbus-1/services/net.bacamt.otprunner.service"
    old.parent.mkdir(parents=True)
    old.write_text("[D-BUS Service]\nName=net.bacamt.otprunner\nExec=/usr/bin/python3 -m otprunner serve\n")
    assert install.install(verbose=False) == 0
    assert not old.exists()
    new = install.paths()["dbus"]
    assert new.name == "io.github.baquilla.otprunner.service"
    assert "Name=io.github.baquilla.otprunner" in new.read_text()
    assert "X-Plasma-DBusRunner-Service=io.github.baquilla.otprunner" in install.paths()["runner"].read_text()
