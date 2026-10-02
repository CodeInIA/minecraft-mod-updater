"""Shared test setup.

The configuration folder is computed when updater_core is imported, so the
environment is pointed at a temporary folder before any app module is loaded.
Tests never touch the real user configuration.
"""

import os
import sys
import tempfile

_TMP_HOME = tempfile.mkdtemp(prefix="mmu-tests-")
os.environ["APPDATA"] = _TMP_HOME            # Windows
os.environ["HOME"] = _TMP_HOME               # macOS / Linux
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP_HOME, ".config")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402

import updater_core as core  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs internet access (Modrinth / GitHub)")
    config.addinivalue_line("markers", "gui: needs a display (Tk)")


@pytest.fixture
def fresh_config():
    """Start every test that uses it without a saved configuration."""
    if os.path.exists(core.CONFIG_FILE):
        os.remove(core.CONFIG_FILE)
    yield
    if os.path.exists(core.CONFIG_FILE):
        os.remove(core.CONFIG_FILE)
