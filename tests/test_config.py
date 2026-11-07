"""Test configuration and basic imports."""

import pytest
from src.config.settings import Settings, get_settings


def test_settings_defaults():
    """Test default settings values."""
    settings = Settings()

    assert settings.MODE == "dev"
    assert settings.IB_HOST == "127.0.0.1"
    assert settings.IB_PORT == 4002
    assert settings.STRATEGY_NAME == "smc"
    assert settings.DASHBOARD_ENABLED is True


def test_settings_symbols_parsing():
    """Test symbol list parsing."""
    settings = Settings(DEFAULT_SYMBOLS="SPY, QQQ, AAPL")
    assert settings.DEFAULT_SYMBOLS == ["SPY", "QQQ", "AAPL"]


def test_get_settings_singleton():
    """Test settings singleton."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2