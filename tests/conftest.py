"""Configuration file for pytest fixtures in custom integration tests."""

import os
import sys

import pytest

# Insert the repository root (one level up from tests folder) into sys.path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable custom integrations for all tests."""
    yield
