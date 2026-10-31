"""Tests for the Daikin fan speed select."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_br.const import DOMAIN, FAN_MODES
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


def test_options_and_default(config_entry):
    """The select offers the climate fan modes and starts disabled."""
    fan_speed = DaikinFanSpeed(config_entry)

    assert fan_speed.options == FAN_MODES
    assert len(fan_speed.options) == 7
    assert fan_speed.entity_registry_enabled_default is False


@pytest.mark.parametrize(
    ("fan", "option"),
    [
        (17, "auto"),
        (7, "high"),
        (6, "medium_high"),
        (5, "medium"),
        (4, "low_medium"),
        (3, "low"),
        (18, "quiet"),
    ],
)
def test_current_option(config_entry, fan, option):
    """Every device fan value maps to the same option as the climate fan mode."""
    config_entry.runtime_data.data["port1"]["fan"] = fan
    assert DaikinFanSpeed(config_entry).current_option == option


def test_current_option_without_fan(config_entry):
    """No fan value reported means no current option."""
    del config_entry.runtime_data.data["port1"]["fan"]
    assert DaikinFanSpeed(config_entry).current_option is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("option", "fan"),
    [("auto", 17), ("high", 7), ("medium", 5), ("low", 3), ("quiet", 18)],
)
async def test_select_option(config_entry, option, fan):
    """Selecting an option sends the matching device value."""
    fan_speed = DaikinFanSpeed(config_entry)

    await fan_speed.async_select_option(option)

    config_entry.runtime_data.async_send_command.assert_awaited_once_with(fan=fan)


@pytest.mark.asyncio
@pytest.mark.parametrize("port_update", [{"mode": 2}, {"powerchill": 1}])
async def test_select_blocked(config_entry, port_update):
    """Fan speed is locked in dry mode and while Power Chill is on."""
    config_entry.runtime_data.data["port1"].update(port_update)
    fan_speed = DaikinFanSpeed(config_entry)

    with pytest.raises(HomeAssistantError):
        await fan_speed.async_select_option("low")
    config_entry.runtime_data.async_send_command.assert_not_awaited()
