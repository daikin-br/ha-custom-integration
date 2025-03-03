"""Tests for the Daikin BR coordinator."""

import datetime
import logging
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_br.coordinator import DaikinDataUpdateCoordinator


# Dummy hass fixture for testing.
@pytest.fixture
def dummy_hass():
    """Create a dummy hass object for testing."""
    return MagicMock()


# Test case 1: Valid data returned by update_method.
@pytest.mark.asyncio
async def test_async_update_data_valid(dummy_hass):
    """Test _async_update_data returns valid data when update_method returns a dict."""

    async def update_method():
        return {"port1": {"fw_ver": "1.0.0", "temperature": 22}}

    coordinator = DaikinDataUpdateCoordinator(
        dummy_hass,
        device_apn="TEST_APN",
        update_method=update_method,
        update_interval=datetime.timedelta(seconds=10),
    )

    data = await coordinator._async_update_data()
    assert isinstance(data, dict)
    assert data == {"port1": {"fw_ver": "1.0.0", "temperature": 22}}


# Test case 2: Non-dict value returned by update_method.
@pytest.mark.asyncio
async def test_async_update_data_invalid_type(dummy_hass, caplog):
    """
    Test _async_update_data returns {}.

    Logs debug when update_method returns a non-dict.
    """

    async def update_method():
        return "invalid"  # not a dict

    coordinator = DaikinDataUpdateCoordinator(
        dummy_hass,
        device_apn="TEST_APN",
        update_method=update_method,
        update_interval=datetime.timedelta(seconds=10),
    )
    caplog.set_level(logging.DEBUG)
    data = await coordinator._async_update_data()
    assert data == {}
    # Check that the expected debug message is in the log.
    assert "Unable to retrieve device status data for TEST_APN" in caplog.text


# Test case 3: Exception raised by update_method.
@pytest.mark.asyncio
async def test_async_update_data_exception(dummy_hass, caplog):
    """
    Test _async_update_data returns {}.

    Logs debug when update_method raises an exception.
    """

    async def update_method():
        raise Exception("Test exception")

    coordinator = DaikinDataUpdateCoordinator(
        dummy_hass,
        device_apn="TEST_APN",
        update_method=update_method,
        update_interval=datetime.timedelta(seconds=10),
    )
    caplog.set_level(logging.DEBUG)
    data = await coordinator._async_update_data()
    assert data == {}
    # Check that the debug message is logged indicating an error.
    assert "Error fetching data for TEST_APN:" in caplog.text
