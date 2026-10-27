"""Tests for the Daikin fan speed select."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_br.const import DOMAIN
from custom_components.daikin_br.select import DaikinFanSpeed
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError


# pylint: disable=redefined-outer-name
@pytest.fixture
def config_entry():
    """Create a config entry whose AC is cooling at full speed."""
    coordinator = MagicMock()
    coordinator.data = {"port1": {"mode": 3, "fan": 7, "powerchill": 0}}
    coordinator.last_update_success = True
    coordinator.async_send_command = AsyncMock()
    entry = MagicMock(spec=ConfigEntry)
    entry.domain = DOMAIN
    entry.data = {"device_apn": "TEST_APN", "device_name": "TEST DEVICE"}
    entry.runtime_data = coordinator
    return entry


def test_current_option(config_entry):
    """Device fan values map to named options."""
    fan_speed = DaikinFanSpeed(config_entry)
    assert fan_speed.current_option == "speed_5"

    config_entry.runtime_data.data["port1"]["fan"] = 18
    assert fan_speed.current_option == "quiet"

    config_entry.runtime_data.data["port1"]["fan"] = 99
    assert fan_speed.current_option is None


@pytest.mark.asyncio
async def test_select_option(config_entry):
    """Selecting an option sends the matching device value."""
    fan_speed = DaikinFanSpeed(config_entry)

    await fan_speed.async_select_option("auto")

    config_entry.runtime_data.async_send_command.assert_awaited_once_with(fan=17)


@pytest.mark.asyncio
@pytest.mark.parametrize("port_update", [{"mode": 2}, {"powerchill": 1}])
async def test_select_blocked(config_entry, port_update):
    """Fan speed is locked in dry mode and while Power Chill is on."""
    config_entry.runtime_data.data["port1"].update(port_update)
    fan_speed = DaikinFanSpeed(config_entry)

    with pytest.raises(HomeAssistantError):
        await fan_speed.async_select_option("speed_1")
    config_entry.runtime_data.async_send_command.assert_not_awaited()
