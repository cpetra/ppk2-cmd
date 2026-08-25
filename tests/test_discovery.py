import os
from ppk2_cmd.discovery import get_active_ppk2_port


def test_env_port_override(monkeypatch):
    # Test that PPK2_PORT environment variable takes precedence without probing
    monkeypatch.setenv("PPK2_PORT", "/dev/custom_port_123")
    port = get_active_ppk2_port()
    assert port == "/dev/custom_port_123"


def test_explicit_port_overrides_env(monkeypatch):
    # Test that explicit parameter overrides PPK2_PORT in .env
    monkeypatch.setenv("PPK2_PORT", "/dev/custom_port_123")
    port = get_active_ppk2_port(user_port="/dev/cli_override")
    assert port == "/dev/cli_override"
