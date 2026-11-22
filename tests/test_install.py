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
