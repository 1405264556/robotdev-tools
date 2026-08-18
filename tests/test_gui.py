from unittest.mock import patch

from robotdev_tools.gui import tkinter_install_hint


def test_linux_tkinter_hint_has_package_commands() -> None:
    with patch("platform.system", return_value="Linux"):
        hint = tkinter_install_hint()
    assert "python3-tk" in hint
    assert "apt install" in hint


def test_windows_tkinter_hint_mentions_python_installer() -> None:
    with patch("platform.system", return_value="Windows"):
        hint = tkinter_install_hint()
    assert "python.org" in hint
    assert "Tcl/Tk" in hint
