import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "packaging/kde-store"

pytestmark = pytest.mark.skipif(not shutil.which("sh") or not shutil.which("python3"), reason="needs sh and python3")


def run(script, tmp_path, lang="C", tools=("python3",)):
    """Runs a store script with a PATH that only has the given tools, and no terminal."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for tool in tools:
        fake = tmp_path / tool  # a fake made by the test, else the real one
        (bin_dir / tool).symlink_to(fake if fake.exists() else shutil.which(tool))
    env = {"HOME": str(tmp_path), "PATH": str(bin_dir), "LANG": lang}
    sh = shutil.which("sh")
    r = subprocess.run([sh, STORE / script], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_install_explains_without_installing(tmp_path):
    out = run("install.sh", tmp_path)
    assert "does not install anything" in out
    assert "✗ pipx" in out and "sudo apt install" in out
    assert "pipx install OTPRunner" in out and "otprunner install" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin"]  # nothing written


def test_install_with_pipx_and_spanish(tmp_path):
    fake = tmp_path / "pipx"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    out = run("install.sh", tmp_path, lang="es_ES.UTF-8", tools=("python3", "pipx"))
    assert "no instala nada" in out and "✓ pipx" in out and "sudo apt" not in out


def test_install_when_already_installed(tmp_path):
    fake = tmp_path / "otprunner"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    plugin = tmp_path / ".local/share/krunner/dbusplugins/otprunner.desktop"
    plugin.parent.mkdir(parents=True)
    plugin.touch()
    out = run("install.sh", tmp_path, tools=("python3", "otprunner"))
    assert "already installed" in out and "pipx upgrade otprunner" in out


def test_uninstall_removes_nothing(tmp_path):
    out = run("uninstall.sh", tmp_path)
    assert "nothing else to remove" in out and "not installed" in out


def test_archive_is_flat_and_executable(tmp_path):
    if not shutil.which("tar"):
        pytest.skip("needs tar")
    path = subprocess.run([ROOT / "scripts/kde-store.sh"], cwd=ROOT, capture_output=True, text=True, check=True)
    with tarfile.open(ROOT / path.stdout.strip()) as tar:
        members = {m.name: m.mode for m in tar.getmembers()}
    assert set(members) == {"README", "install.sh", "uninstall.sh"}
    assert members["install.sh"] & 0o111 and members["uninstall.sh"] & 0o111
