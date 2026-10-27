"""Tests for the Daikin switch entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_br.const import DOMAIN
from custom_components.daikin_br.switch import SWITCHES, DaikinSwitch, async_setup_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

DESCRIPTIONS = {description.key: description for description in SWITCHES}


# pylint: disable=redefined-outer-name
@pytest.fixture
def coordinator():
    """Create a coordinator reporting a running AC."""
    coordinator = MagicMock()
    coordinator.data = {
        "port1": {
            "power": 1,
            "powerchill": 0,
            "econo": 1,
            "v_swing": 1,
            "streamer": 0,
            "good_sleep": 0,
            "fw_ver": "p1.0.4.2",
        }
    }
    coordinator.capabilities = {}
    coordinator.last_update_success = True
    coordinator.async_send_command = AsyncMock()
    return coordinator


@pytest.fixture
def config_entry(coordinator):
    """Create a config entry carrying the coordinator."""
    entry = MagicMock(spec=ConfigEntry)
    entry.domain = DOMAIN
    entry.data = {"device_apn": "TEST_APN", "device_name": "TEST DEVICE"}
    entry.runtime_data = coordinator
    return entry


@pytest.mark.asyncio
async def test_setup_skips_unsupported_swing(hass: HomeAssistant, config_entry):
    """Units reporting v_sw=0 get no vertical swing switch."""
    config_entry.runtime_data.capabilities = {"v_sw": 0}
    async_add_entities = MagicMock()

    await async_setup_entry(hass, config_entry, async_add_entities)

    keys = [
        entity.entity_description.key for entity in async_add_entities.call_args[0][0]
    ]
    assert "v_swing" not in keys
    assert keys == [key for key in DESCRIPTIONS if key != "v_swing"]


def test_state_and_unique_id(config_entry):
    """Switch state mirrors the device field and ids are per feature."""
    econo = DaikinSwitch(config_entry, DESCRIPTIONS["econo"])
    streamer = DaikinSwitch(config_entry, DESCRIPTIONS["streamer"])

    assert econo.is_on is True
    assert streamer.is_on is False
    assert econo.unique_id == "TEST_APN_econo"
    assert econo.device_info["identifiers"] == {(DOMAIN, "TEST_APN")}


def test_unavailable_when_field_missing(config_entry):
    """A field the device does not report makes the switch unavailable."""
    del config_entry.runtime_data.data["port1"]["good_sleep"]
    switch = DaikinSwitch(config_entry, DESCRIPTIONS["good_sleep"])

    assert switch.available is False


@pytest.mark.asyncio
async def test_turn_on_and_off(config_entry):
    """Turning a switch on and off sends its field."""
    coordinator = config_entry.runtime_data
    switch = DaikinSwitch(config_entry, DESCRIPTIONS["streamer"])

    await switch.async_turn_on()
    coordinator.async_send_command.assert_awaited_once_with(streamer=1)
    coordinator.async_send_command.reset_mock()

    await switch.async_turn_off()
    coordinator.async_send_command.assert_awaited_once_with(streamer=0)


@pytest.mark.asyncio
async def test_boost_turns_off_eco(config_entry):
    """Power Chill and Econo are exclusive: enabling one disables the other."""
    coordinator = config_entry.runtime_data
    switch = DaikinSwitch(config_entry, DESCRIPTIONS["powerchill"])

    await switch.async_turn_on()

    coordinator.async_send_command.assert_awaited_once_with(powerchill=1, econo=0)


@pytest.mark.asyncio
async def test_requires_power(config_entry):
    """Preset switches refuse to turn on while the AC is off."""
    coordinator = config_entry.runtime_data
    coordinator.data["port1"]["power"] = 0
    switch = DaikinSwitch(config_entry, DESCRIPTIONS["powerchill"])

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()
    coordinator.async_send_command.assert_not_awaited()
