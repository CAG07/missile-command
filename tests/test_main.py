"""
Tests for main.py -- the thin CLI entry point.

Application logic lives in src/app.py (see tests/test_app.py);
these tests just confirm main.py exists and wires through correctly.
"""

import os

import main
from src.app import MissileCommandApp, parse_args


class TestEntryPoint:
    def test_main_py_exists(self):
        """main.py must exist as the game entry point."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assert os.path.isfile(os.path.join(root, "main.py"))

    def test_reexports_parse_args(self):
        assert main.parse_args is parse_args

    def test_reexports_missile_command_app(self):
        assert main.MissileCommandApp is MissileCommandApp

    def test_main_returns_error_code_without_pygame_display(self, monkeypatch):
        """If app initialisation fails, main() should return a non-zero
        exit code rather than raising."""
        monkeypatch.setattr(MissileCommandApp, "init", lambda self: False)
        assert main.main([]) == 1
