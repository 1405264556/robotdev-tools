from unittest.mock import patch

import pytest

from robotdev_tools.gui import format_size, tkinter_install_hint


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


@pytest.mark.parametrize(
    "size,expected",
    [(0, "0 B"), (1024, "1.0 KiB"), (1024 * 1024, "1.0 MiB")],
)
def test_format_size(size: int, expected: str) -> None:
    assert format_size(size) == expected
