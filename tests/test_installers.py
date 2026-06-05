from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_linux_desktop_launcher_sets_working_directory():
    install_sh = (ROOT / "install.sh").read_text()

    assert 'Exec="$HERE/.venv/bin/python" -m a0_ui' in install_sh
    assert "Path=$HERE" in install_sh
