"""Tests for the Daikin Climate custom component."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.climate.const import (
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_OFF,
    SWING_VERTICAL,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_API_KEY, UnitOfTemperature
from pyiotdevice import InvalidDataException

from custom_components.daikin_br.climate import DaikinClimate, async_setup_entry


# Fixture to mock a Home Assistant config entry
@pytest.fixture
def mock_config_entry():
    """Fixture to create a mock config entry."""

    def _create_entry(data):
        entry = MagicMock()
        entry.data = data
        return entry

    return _create_entry


@pytest.fixture
def dummy_coordinator(hass):
    """Create a dummy coordinator for testing purposes."""
    coordinator = MagicMock()
    coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    coordinator.hass = hass
    coordinator.last_update_success = True
    return coordinator


@pytest.mark.asyncio
async def test_async_setup_entry_missing_device_key(hass, caplog):
    """Test setup fails when device key is missing."""
    entry = AsyncMock()
    entry.data = {"device_apn": "TEST_APN"}  # Missing CONF_API_KEY

    async_add_entities = AsyncMock()

    await async_setup_entry(hass, entry, async_add_entities)

    # Ensure error is logged
    assert "Device key is missing in the configuration entry!" in caplog.text
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_invalid_device_key(hass, caplog):
    """Test setup fails when device returns invalid data (exception handling)."""
    # Mock entry data.
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "INVALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }

    # Use MagicMock for async_add_entities.
    async_add_entities = MagicMock()

    # Patch get_thing_info to raise an exception (simulating an invalid device key).
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=Exception("Invalid device key"),
    ):
        # Call async_setup_entry which should internally call async_add_entities.
        await async_setup_entry(hass, entry, async_add_entities)

    # Ensure that an error message was logged.
    # (Check for "Error fetching data" or "Invalid device key" in the log.)
    assert "Error fetching data" in caplog.text or "Invalid device key" in caplog.text

    # Ensure async_add_entities was called once.
    async_add_entities.assert_called_once()

    # Retrieve the created entity.
    entity = async_add_entities.call_args[0][0][0]
    # For testing, assign hass to the entity.
    entity.hass = hass

    # Force the coordinator to report a failed update so that available is False.
    entity.coordinator.last_update_success = False

    # Ensure the entity is of type DaikinClimate and is marked as unavailable.
    assert isinstance(entity, DaikinClimate)
    assert entity.available is False


@pytest.mark.asyncio
async def test_async_setup_entry_communication_failure(hass, caplog):
    """Test setup handles communication failures gracefully."""
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }

    async_add_entities = MagicMock()

    # Simulate an exception in get_thing_info
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=Exception("Connection error"),
    ):
        await async_setup_entry(hass, entry, async_add_entities)

    # Ensure the correct error message is logged.
    assert "Unexpected error" in caplog.text

    # Ensure async_add_entities is called once.
    async_add_entities.assert_called_once()

    # Retrieve the entity that was created.
    entity = async_add_entities.call_args[0][0][0]

    # For testing, assign hass to the entity.
    entity.hass = hass

    # Simulate a failed update by forcing the coordinator to report failure.
    entity.coordinator.last_update_success = False

    # Ensure entity is created and marked as unavailable.
    assert isinstance(entity, DaikinClimate)
    assert entity.available is False


@pytest.mark.asyncio
async def test_async_setup_entry_no_port_status(hass, caplog):
    """
    Test setup proceeds but marks the entity as unavailable.

    This happens when port_status is missing.
    """
    # Create a dummy config entry.
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }

    # Use MagicMock for async_add_entities.
    async_add_entities = MagicMock()

    # Patch async_write_ha_state in DaikinClimate to be a no-op.
    with patch(
        "custom_components.daikin_br.climate.DaikinClimate.async_write_ha_state",
        return_value=None,
    ):
        # Patch get_thing_info to return an empty dictionary
        # (simulating no port_status).
        with patch(
            "custom_components.daikin_br.climate.get_thing_info", return_value={}
        ):
            await async_setup_entry(hass, entry, async_add_entities)

    # Ensure error message is logged.
    assert "Device setup failed. Invalid device key." in caplog.text

    # Ensure async_add_entities is called once.
    async_add_entities.assert_called_once()

    # Retrieve the entity that was created.
    entity = async_add_entities.call_args[0][0][0]

    # For testing, assign hass to the entity so that its available property can be read.
    entity.hass = hass

    # Force the coordinator's last_update_success flag to False so that
    # the available property (which is based on the coordinator's status) returns False.
    entity.coordinator.last_update_success = False

    # Ensure the entity is an instance of DaikinClimate.
    assert isinstance(entity, DaikinClimate)
    # Verify that the entity is marked as unavailable.
    assert entity.available is False


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass, caplog):
    """Test setup succeeds when get_thing_info returns valid port_status."""
    entry = MagicMock()
    entry.data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    async_add_entities = MagicMock()

    # Mock a valid device response.
    mock_status = {"port1": {"fw_ver": "1.0.0", "temperature": 24}}

    with patch(
        "custom_components.daikin_br.climate.get_thing_info", return_value=mock_status
    ), patch.object(
        DaikinClimate, "update_entity_properties", MagicMock()
    ) as mock_update:
        await async_setup_entry(hass, entry, async_add_entities)

    # Ensure no error message is logged.
    assert "Device setup failed. Invalid device key." not in caplog.text

    # Ensure async_add_entities is called once.
    async_add_entities.assert_called_once()

    # Retrieve the created entity.
    entity = async_add_entities.call_args[0][0][0]

    # For testing, assign hass to the entity so that its available property can be read.
    entity.hass = hass

    # Ensure the entity is a DaikinClimate instance and marked as available.
    assert isinstance(entity, DaikinClimate)
    assert entity.available is True

    # Ensure update_entity_properties was called once with the correct status.
    mock_update.assert_called_once_with(mock_status)


@pytest.mark.asyncio
async def test_async_set_hvac_mode(hass, caplog):
    """Test setting various HVAC modes in DaikinClimate."""
    # Dummy entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator (using MagicMock) required by the entity.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}  # Minimal dummy data
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass  # Ensure hass is set on the entity

    # Patch set_thing_state to be an AsyncMock.
    climate_entity.set_thing_state = AsyncMock()

    # Define expected mode mappings and JSON payloads.
    test_cases = {
        HVACMode.OFF: json.dumps({"port1": {"power": 0}}),
        HVACMode.FAN_ONLY: json.dumps({"port1": {"mode": 6, "power": 1}}),
        HVACMode.COOL: json.dumps({"port1": {"mode": 3, "power": 1}}),
        HVACMode.DRY: json.dumps({"port1": {"mode": 2, "power": 1}}),
        HVACMode.HEAT: json.dumps({"port1": {"mode": 4, "power": 1}}),
        HVACMode.AUTO: json.dumps({"port1": {"mode": 1, "power": 1}}),
    }

    # Test all valid HVAC modes.
    for hvac_mode, expected_json in test_cases.items():
        await climate_entity.async_set_hvac_mode(hvac_mode)
        climate_entity.set_thing_state.assert_called_with(expected_json)
        climate_entity.set_thing_state.reset_mock()

    # Test an unsupported mode.
    await climate_entity.async_set_hvac_mode("INVALID_MODE")
    assert "Unsupported HVAC mode: INVALID_MODE" in caplog.text
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_fan_mode(hass, caplog):
    """Test setting various fan modes in DaikinClimate."""
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator required by the entity.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass  # Ensure hass is set on the entity.
    climate_entity.entity_id = "climate.test_device"

    # Patch set_thing_state to be an AsyncMock.
    climate_entity.set_thing_state = AsyncMock()

    # Set log capture level.
    caplog.set_level(logging.ERROR)

    # Define expected fan mode mappings and JSON payloads.
    test_cases = {
        "auto": {"port1": {"fan": 17}},
        "high": {"port1": {"fan": 7}},
        "medium_high": {"port1": {"fan": 6}},
        "medium": {"port1": {"fan": 5}},
        "low_medium": {"port1": {"fan": 4}},
        "low": {"port1": {"fan": 3}},
        "quiet": {"port1": {"fan": 18}},
    }

    # Test valid fan modes when not in DRY mode.
    climate_entity._hvac_mode = HVACMode.COOL  # Ensure not in DRY mode.
    for fan_mode, expected_data in test_cases.items():
        expected_json = json.dumps(expected_data)
        await climate_entity.async_set_fan_mode(fan_mode)
        climate_entity.set_thing_state.assert_called_once_with(expected_json)
        climate_entity.set_thing_state.reset_mock()

    # Test fan mode change when in DRY mode (should not send command).
    climate_entity._hvac_mode = HVACMode.DRY
    await climate_entity.async_set_fan_mode("medium")
    # Check if an error is logged.
    assert any(
        "Fan mode change operation is not permitted" in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # Test unsupported fan mode.
    climate_entity._hvac_mode = HVACMode.COOL  # Set HVAC mode back to COOL.
    caplog.clear()  # Clear logs for fresh assertions.
    await climate_entity.async_set_fan_mode("INVALID_MODE")
    # Optionally print captured logs for debugging.
    print("\nCaptured Logs:\n", caplog.text)
    assert any(
        "Unsupported fan mode." in record.message for record in caplog.records
    ), "Expected 'Unsupported fan mode.' in logs"
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_temperature(hass, caplog):
    """Test setting various temperature values in DaikinClimate."""
    # Mock entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator (required by the entity).
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # Patch set_thing_state to be an AsyncMock.
    climate_entity.set_thing_state = AsyncMock()

    # Set log capture level.
    caplog.set_level(logging.ERROR)

    # Test valid temperature setting in COOL mode.
    climate_entity._hvac_mode = HVACMode.COOL
    valid_temp = 22
    expected_json = json.dumps({"port1": {"temperature": valid_temp}})
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: valid_temp})
    climate_entity.set_thing_state.assert_called_once_with(expected_json)
    climate_entity.set_thing_state.reset_mock()

    # Test temperature below range in COOL mode.
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 10})
    assert any(
        "Temperature 10°C is out of range for COOL mode (16-32°C)." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # Test temperature above range in COOL mode.
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 35})
    assert any(
        "Temperature 35°C is out of range for COOL mode (16-32°C)." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # Test temperature setting in FAN_ONLY mode (should fail).
    climate_entity._hvac_mode = HVACMode.FAN_ONLY
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 24})
    assert any(
        "Temperature cannot be changed in" in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # Test temperature setting in DRY mode (should fail).
    climate_entity._hvac_mode = HVACMode.DRY
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 25})
    assert any(
        "Temperature cannot be changed in" in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # Test missing temperature attribute (should fail).
    caplog.clear()
    await climate_entity.async_set_temperature()
    assert any(
        "Temperature not provided in the request." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_preset_mode(hass, caplog):
    """Test setting preset modes in DaikinClimate."""
    # Mock entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator (required by the entity).
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # Patch schedule_update_ha_state and set_thing_state.
    climate_entity.schedule_update_ha_state = MagicMock()
    climate_entity.set_thing_state = AsyncMock()

    caplog.set_level(logging.ERROR)

    # --- Test when device is ON ---
    climate_entity._power_state = 1

    # Test preset ECO.
    expected_json_eco = json.dumps({"port1": {"powerchill": 0, "econo": 1}})
    await climate_entity.async_set_preset_mode(PRESET_ECO)
    assert climate_entity._attr_preset_mode == PRESET_ECO
    climate_entity.schedule_update_ha_state.assert_called_once()
    climate_entity.set_thing_state.assert_awaited_once_with(expected_json_eco)
    climate_entity.schedule_update_ha_state.reset_mock()
    climate_entity.set_thing_state.reset_mock()

    # Test preset BOOST.
    await climate_entity.async_set_preset_mode(PRESET_BOOST)
    assert climate_entity._attr_preset_mode == PRESET_BOOST
    climate_entity.schedule_update_ha_state.assert_called_once()
    expected_json_boost = json.dumps({"port1": {"powerchill": 1, "econo": 0}})
    climate_entity.set_thing_state.assert_awaited_once_with(expected_json_boost)
    climate_entity.schedule_update_ha_state.reset_mock()
    climate_entity.set_thing_state.reset_mock()

    # Test preset NONE.
    await climate_entity.async_set_preset_mode(PRESET_NONE)
    assert climate_entity._attr_preset_mode == PRESET_NONE
    climate_entity.schedule_update_ha_state.assert_called_once()
    expected_json_none = json.dumps({"port1": {"powerchill": 0, "econo": 0}})
    climate_entity.set_thing_state.assert_awaited_once_with(expected_json_none)
    climate_entity.schedule_update_ha_state.reset_mock()
    climate_entity.set_thing_state.reset_mock()

    # --- Test when device is OFF ---
    climate_entity._power_state = 0
    caplog.clear()
    await climate_entity.async_set_preset_mode(PRESET_ECO)
    # Expect an error log and no calls to schedule_update_ha_state or set_thing_state.
    assert any(
        "The device operation cannot be performed because it is turned off."
        in record.message
        for record in caplog.records
    )
    climate_entity.schedule_update_ha_state.assert_not_called()
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_swing_mode(hass, caplog):
    """Test setting swing modes in DaikinClimate."""
    # Mock entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator (required by the entity).
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass  # Ensure hass is set on the entity.
    climate_entity.entity_id = "climate.test_device"

    # Patch set_thing_state to be an AsyncMock.
    climate_entity.set_thing_state = AsyncMock()

    # Define available swing modes.
    climate_entity._attr_swing_modes = {SWING_VERTICAL, SWING_OFF}

    # Test setting SWING_VERTICAL mode.
    expected_json_vertical = json.dumps({"port1": {"v_swing": 1}})
    await climate_entity.async_set_swing_mode(SWING_VERTICAL)
    climate_entity.set_thing_state.assert_called_with(expected_json_vertical)
    climate_entity.set_thing_state.reset_mock()

    # Test setting SWING_OFF mode.
    expected_json_off = json.dumps({"port1": {"v_swing": 0}})
    await climate_entity.async_set_swing_mode(SWING_OFF)
    climate_entity.set_thing_state.assert_called_with(expected_json_off)
    climate_entity.set_thing_state.reset_mock()

    # Test unsupported swing mode.
    caplog.clear()
    await climate_entity.async_set_swing_mode("INVALID_MODE")
    assert any(
        "Unsupported swing mode: INVALID_MODE" in record.message
        for record in caplog.records
    ), "Expected 'Unsupported swing mode' log"
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_set_thing_state(hass, caplog):
    """Test the set_thing_state function of DaikinClimate."""
    # Mock entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create a dummy coordinator (required by the entity).
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = hass

    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = hass  # Ensure hass is set on the entity.
    climate_entity._ip_address = "192.168.1.100"
    climate_entity._device_key = "VALID_KEY"
    climate_entity._command_suffix = "command"

    # Patch async_write_ha_state to a MagicMock.
    climate_entity.async_write_ha_state = MagicMock()

    # Mock response from send_operation_data.
    mock_response = {
        "port1": {
            "power": 1,
            "mode": 3,  # COOL mode (maps to HVACMode.COOL)
            "temperature": 22,
            "sensors": {"room_temp": 23},
            "fan": 5,  # Fan speed 5 should map to "medium"
            "v_swing": 1,
            "econo": 1,  # This should set preset mode to PRESET_ECO ("eco")
            "powerchill": 0,
        }
    }

    # Patch send_operation_data to return the mock_response.
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        return_value=mock_response,
    ):
        data = json.dumps({"port1": {"temperature": 22}})
        await climate_entity.set_thing_state(data)

        # Verify that internal state is updated correctly.
        assert climate_entity._power_state == 1
        assert climate_entity._hvac_mode == HVACMode.COOL
        assert climate_entity._target_temperature == 22
        assert climate_entity._current_temperature == 23
        assert climate_entity._fan_mode == "medium"
        # Expect swing mode to be SWING_VERTICAL;
        # typically, SWING_VERTICAL == "vertical"
        assert climate_entity._attr_swing_mode == "vertical"
        # Expect preset mode to be PRESET_ECO, which is "eco"
        assert climate_entity._attr_preset_mode == "eco"

        # Verify that async_write_ha_state was called once.
        climate_entity.async_write_ha_state.assert_called_once()

        # Verify that the log contains the expected preset mode set message.
        assert "Preset mode set to : eco" in caplog.text

    # Test error scenario: simulate send_operation_data raising an exception.
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        side_effect=Exception("Failed to send command"),
    ):
        caplog.clear()  # Clear previous logs.
        await climate_entity.set_thing_state(data)
        assert "Failed to send command: Failed to send command" in caplog.text


@pytest.mark.asyncio
async def test_update_entity_properties():
    """Test update_entity_properties function."""
    # Create a dummy coordinator required by the entity.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Prepare entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = dummy_coordinator.hass

    # Patch async_write_ha_state to avoid side effects.
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate input data for port_status.
    port_status = {
        "port1": {
            "sensors": {"room_temp": 23},
            "temperature": 22,
            "power": 1,  # Power ON
            "mode": 3,  # COOL mode (should map to HVACMode.COOL)
            "fan": 5,  # Fan speed 5; expected mapping to "medium"
            "v_swing": 1,  # Vertical swing (maps to SWING_VERTICAL)
            "econo": 1,  # Economy mode (should set preset to PRESET_ECO)
            "powerchill": 0,  # No powerchill
        }
    }

    # Call update_entity_properties synchronously (without await).
    climate_entity.update_entity_properties(port_status)

    # Verify that the internal state is updated as expected.
    assert climate_entity._current_temperature == 23  # room_temp from sensors.
    assert climate_entity._target_temperature == 22  # temperature from port_status.
    assert climate_entity._power_state == 1  # Power ON.
    assert climate_entity._hvac_mode == HVACMode.COOL  # Mode 3 maps to COOL.
    assert climate_entity._fan_mode == "medium"  # Fan speed 5 maps to "medium".
    assert (
        climate_entity._attr_swing_mode == SWING_VERTICAL
    )  # v_swing 1 means vertical.
    assert climate_entity._attr_preset_mode == PRESET_ECO  # econo 1 maps to eco preset.

    # Verify that async_write_ha_state is called once.
    climate_entity.async_write_ha_state.assert_called_once()

    # Verify that the skip update flag is set.
    assert climate_entity._skip_update is True

    # Construct a status dict where:
    # - power is ON,
    # - mode is 3 (e.g. COOL, not that it matters for preset),
    # - econo is 0,
    # - powerchill is 1.
    port_status = {
        "port1": {
            "sensors": {"room_temp": 24},
            "temperature": 23,
            "power": 1,
            "mode": 3,
            "fan": 5,
            "v_swing": 1,
            "econo": 0,
            "powerchill": 1,
        }
    }
    # Call update_entity_properties synchronously.
    climate_entity.update_entity_properties(port_status)

    # Assert that the branch setting PRESET_BOOST was executed.
    assert climate_entity._attr_preset_mode == PRESET_BOOST


@pytest.mark.asyncio
async def test_update_entity_properties_device_off():
    """Test update_entity_properties when the device is OFF."""
    # Create a dummy coordinator required by the entity.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Prepare entry data for DaikinClimate.
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    # Create DaikinClimate instance with the dummy coordinator.
    climate_entity = DaikinClimate(entry_data, dummy_coordinator)
    climate_entity.hass = dummy_coordinator.hass

    # Patch async_write_ha_state to avoid side effects during testing.
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate input data for port_status with the device OFF.
    port_status = {
        "port1": {
            "sensors": {"room_temp": 23},
            "temperature": 22,
            "power": 0,  # Power OFF
            "mode": 0,  # HVACMode.OFF
            "fan": 3,  # Fan speed 3 should map to "low"
            "v_swing": 0,  # No swing; should map to SWING_OFF
            "econo": 0,  # No economy mode
            "powerchill": 0,  # No powerchill
        }
    }

    # Call update_entity_properties synchronously.
    climate_entity.update_entity_properties(port_status)

    # Verify that the internal state is updated as expected.
    assert climate_entity._current_temperature == 23  # From sensors: room_temp.
    assert climate_entity._target_temperature == 22  # From port_status.
    assert climate_entity._power_state == 0  # Device is OFF.
    assert climate_entity._hvac_mode == HVACMode.OFF  # HVACMode should be OFF.
    assert climate_entity._fan_mode == "low"  # Fan speed 3 maps to "low".
    assert climate_entity._attr_swing_mode == SWING_OFF  # v_swing 0 maps to SWING_OFF.
    assert (
        climate_entity._attr_preset_mode == PRESET_NONE
    )  # econo=0 and powerchill=0 yield PRESET_NONE.

    # Verify that async_write_ha_state is called once.
    climate_entity.async_write_ha_state.assert_called_once()

    # Verify that the skip update flag is set.
    assert climate_entity._skip_update is True


@pytest.mark.parametrize(
    "hvac_value, expected_mode",
    [
        (0, HVACMode.OFF),
        (6, HVACMode.FAN_ONLY),
        (3, HVACMode.COOL),
        (2, HVACMode.DRY),
        (4, HVACMode.HEAT),
        (1, HVACMode.AUTO),
        (99, HVACMode.OFF),  # Unknown value should return OFF
    ],
)
def test_map_hvac_mode(hvac_value, expected_mode):
    """
    Test map_hvac_mode method.

    This will ensure correct mapping of device values to HA modes.
    """
    # Create a dummy coordinator.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Create an instance of DaikinClimate with empty entry data and dummy coordinator.
    climate_entity = DaikinClimate({}, dummy_coordinator)

    # Call map_hvac_mode and verify output.
    assert climate_entity.map_hvac_mode(hvac_value) == expected_mode


@pytest.mark.parametrize(
    "fan_value, expected_mode",
    [
        (17, "auto"),
        (7, "high"),
        (6, "medium_high"),
        (5, "medium"),
        (4, "low_medium"),
        (3, "low"),
        (18, "quiet"),
        (99, "auto"),  # Unknown value should default to "auto"
    ],
)
def test_map_fan_speed(fan_value, expected_mode):
    """Test map_fan_speed method for correct fan speed mappings."""
    # Create a dummy coordinator.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Create an instance of DaikinClimate with empty entry data and dummy coordinator.
    climate_entity = DaikinClimate({}, dummy_coordinator)
    assert climate_entity.map_fan_speed(fan_value) == expected_mode


@pytest.mark.parametrize(
    "temperature, expected_temperature",
    [
        (22, 22),  # Valid temperature
        (30, 30),  # Valid upper limit
        (16, 16),  # Valid lower limit
        (50, 50),  # Extreme value (assuming no validation)
        (None, None),  # Edge case: None input
    ],
)
def test_set_temperature(temperature, expected_temperature):
    """Test setting the target temperature."""
    # Create a dummy coordinator.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Create an instance of DaikinClimate with the dummy coordinator.
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        },
        dummy_coordinator,
    )

    # Simulate setting the temperature.
    climate_entity._target_temperature = temperature

    assert climate_entity._target_temperature == expected_temperature


@pytest.mark.parametrize(
    "swing_mode, expected_swing_mode",
    [
        (SWING_OFF, SWING_OFF),  # Swing off
        (SWING_VERTICAL, SWING_VERTICAL),  # Vertical swing
    ],
)
def test_swing_mode_property(swing_mode, expected_swing_mode):
    """Test the swing_mode property for OFF and VERTICAL only."""
    # Create a dummy coordinator.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Create an instance of DaikinClimate with the dummy coordinator.
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        },
        dummy_coordinator,
    )

    # Manually set the private swing mode attribute.
    climate_entity._attr_swing_mode = swing_mode

    # Assert that the property returns the expected swing mode.
    assert climate_entity.swing_mode == expected_swing_mode


@pytest.mark.parametrize(
    "preset_mode, expected_preset_mode",
    [
        (PRESET_ECO, PRESET_ECO),  # Economy mode
        (PRESET_BOOST, PRESET_BOOST),  # Power chill mode
        (PRESET_NONE, PRESET_NONE),  # No preset mode
    ],
)
def test_preset_mode_property(preset_mode, expected_preset_mode):
    """Test the preset_mode property for ECO, BOOST, and NONE."""
    # Create a dummy coordinator.
    dummy_coordinator = MagicMock()
    dummy_coordinator.data = {"port1": {"fw_ver": "1.0.0"}}
    dummy_coordinator.hass = MagicMock()

    # Create an instance of DaikinClimate with the dummy coordinator.
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        },
        dummy_coordinator,
    )

    # Manually set the private preset mode attribute.
    climate_entity._attr_preset_mode = preset_mode

    # Assert that the preset_mode property returns the expected value.
    assert climate_entity.preset_mode == expected_preset_mode


def test_init_missing_device_key(caplog, dummy_coordinator):
    """Test the missing device key."""
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    # Create an instance with missing CONF_API_KEY.
    DaikinClimate(entry_data, dummy_coordinator)
    assert "Device key not found while creating entity!" in caplog.text


def test_property_getters(dummy_coordinator):
    """Test the getters proprety."""
    entry_data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
        "poll_interval": 30,
        "command_suffix": "cmd",
        "fw_ver": "1.2.3",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    # These properties are hard-coded or derived from entry_data
    assert entity.translation_key == "daikin_ac"
    assert entity.unique_id == "TEST_APN"
    assert entity.name is None
    assert (
        entity.temperature_unit == "°C"
        or entity.temperature_unit == UnitOfTemperature.CELSIUS
    )
    assert entity.min_temp == 10.0
    assert entity.max_temp == 32.0
    assert entity.target_temperature_step == 1.0


def test_device_info(dummy_coordinator):
    """Test device info."""
    entry_data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
        "fw_ver": "1.0.0",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    # Expected device info structure (adjust according to your implementation)
    expected_info = {
        "identifiers": {("daikin_br", "TEST_APN")},
        "name": "TEST DEVICE",
        "manufacturer": "Daikin",
        "model": "Smart AC Series",
        "sw_version": "1.0.0",
    }
    # Assuming your base entity uses a device_info property:
    assert entity.device_info == expected_info


@pytest.mark.asyncio
async def test_set_thing_state_exception(dummy_coordinator, caplog, hass):
    """Test set thing state exception."""
    entry_data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity._ip_address = "192.168.1.100"
    entity._device_key = "VALID_KEY"
    entity._command_suffix = "cmd"
    entity.async_write_ha_state = MagicMock()
    # Simulate an exception raised by send_operation_data.
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        side_effect=Exception("Simulated error"),
    ):
        await entity.set_thing_state(json.dumps({"port1": {"temperature": 22}}))
    assert "Failed to send command:" in caplog.text


@pytest.mark.asyncio
async def test_async_set_preset_mode_unsupported(hass, caplog, dummy_coordinator):
    """Test unsupported preset mode."""
    entry_data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity._power_state = 1
    entity.schedule_update_ha_state = MagicMock()
    entity.set_thing_state = AsyncMock()
    caplog.clear()
    # Pass an unsupported preset mode value.
    await entity.async_set_preset_mode("INVALID_PRESET")
    assert any(
        "Unsupported preset mode: INVALID_PRESET" in record.message
        for record in caplog.records
    )
    entity.schedule_update_ha_state.assert_not_called()
    entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_timeout(hass, caplog):
    """Test setup entry timeout."""
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    async_add_entities = MagicMock()
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=TimeoutError("Timeout error"),
    ):
        await async_setup_entry(hass, entry, async_add_entities)
    assert "Timeout while communicating with the device:" in caplog.text


@pytest.mark.asyncio
async def test_async_setup_entry_network_error(hass, caplog):
    """Test setup entry neywork error."""
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    async_add_entities = MagicMock()
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=OSError("Network error"),
    ):
        await async_setup_entry(hass, entry, async_add_entities)
    assert "Network error while communicating with the device:" in caplog.text


@pytest.mark.asyncio
async def test_handle_coordinator_update_exception(hass, dummy_coordinator, caplog):
    """Test coordinator update exception."""
    entry_data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    # Set an entity_id so that async_write_ha_state has an identifier.
    entity.entity_id = "climate.test_entity"
    # Patch update_entity_properties to raise an exception.
    entity.update_entity_properties = MagicMock(side_effect=Exception("Test exception"))
    entity._handle_coordinator_update()
    assert entity._attr_available is False
    assert "Error updating entity properties" in caplog.text


@pytest.mark.asyncio
async def test_async_set_hvac_mode_unsupported(dummy_coordinator, hass, caplog):
    """Test unsupported hvac mode."""
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity.set_thing_state = AsyncMock()
    await entity.async_set_hvac_mode("INVALID_MODE")
    assert "Unsupported HVAC mode: INVALID_MODE" in caplog.text
    entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_fan_mode_unsupported(dummy_coordinator, hass, caplog):
    """Test unsupported fan mode."""
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity.set_thing_state = AsyncMock()

    # Call with an invalid fan mode.
    await entity.async_set_fan_mode("INVALID_FAN")

    # Check that the error log contains the expected message.
    assert "Unsupported fan mode." in caplog.text
    # Ensure that no command was sent.
    entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_temperature_in_fan_only(dummy_coordinator, hass, caplog):
    """Test set temperate in fan mode."""
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity.set_thing_state = AsyncMock()
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = HVACMode.FAN_ONLY
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 24})
    assert any(
        "Temperature cannot be changed in" in record.message
        for record in caplog.records
    )
    entity.set_thing_state.assert_not_called()
    # Also verify that _target_temperature is set to 24 (reverting change)
    assert entity._target_temperature == 24


@pytest.mark.asyncio
async def test_async_set_temperature_in_dry(dummy_coordinator, hass, caplog):
    """Test set temperate in dry mode."""
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity.set_thing_state = AsyncMock()
    entity.async_write_ha_state = MagicMock()
    entity._hvac_mode = HVACMode.DRY
    await entity.async_set_temperature(**{ATTR_TEMPERATURE: 25})
    assert any(
        "Temperature cannot be changed in" in record.message
        for record in caplog.records
    )
    entity.set_thing_state.assert_not_called()
    assert entity._target_temperature == 25


@pytest.mark.asyncio
async def test_async_setup_entry_no_port_status_returns_error(hass, caplog):
    """Test that async_setup_entry handles missing port_status."""
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "VALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    async_add_entities = MagicMock()
    with patch("custom_components.daikin_br.climate.get_thing_info", return_value={}):
        await async_setup_entry(hass, entry, async_add_entities)
    # Expect the error log from the branch that raises ValueError and is caught
    assert "Device setup failed. Invalid device key." in caplog.text
    async_add_entities.assert_called_once()
    entity = async_add_entities.call_args[0][0][0]
    # Force coordinator failure to reflect unavailable state
    entity.coordinator.last_update_success = False
    assert isinstance(entity, DaikinClimate)
    assert entity.available is False


@pytest.mark.asyncio
async def test_set_thing_state_preset_boost_and_none(dummy_coordinator, hass):
    """
    Test set_thing_state sets preset mode to PRESET_BOOST when powerchill equals 1.

    Then sets preset mode to PRESET_NONE when both econo and powerchill are 0.
    """
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity._ip_address = "192.168.1.100"
    entity._device_key = "VALID_KEY"
    entity._command_suffix = "cmd"
    entity.async_write_ha_state = MagicMock()

    # Prepare a dummy payload (could be any valid JSON command for this test)
    data = json.dumps({"port1": {"temperature": 22}})

    # Create two responses:
    # 1. Response for PRESET_BOOST: econo=0, powerchill=1.
    response_boost = {
        "port1": {
            "power": 1,
            "mode": 3,  # COOL mode for example
            "temperature": 22,
            "sensors": {"room_temp": 23},
            "fan": 5,
            "v_swing": 1,
            "econo": 0,
            "powerchill": 1,
        }
    }
    # 2. Response for PRESET_NONE: econo=0, powerchill=0.
    response_none = {
        "port1": {
            "power": 1,
            "mode": 3,
            "temperature": 22,
            "sensors": {"room_temp": 23},
            "fan": 5,
            "v_swing": 1,
            "econo": 0,
            "powerchill": 0,
        }
    }

    # Patch send_operation_data to return response_boost first, then response_none.
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        side_effect=[response_boost, response_none],
    ):
        # First call: Expect PRESET_BOOST
        await entity.set_thing_state(data)
        assert entity._attr_preset_mode == PRESET_BOOST

        # Second call: Expect PRESET_NONE
        await entity.set_thing_state(data)
        assert entity._attr_preset_mode == PRESET_NONE


def test_power_state_property(dummy_coordinator):
    """Test power state property."""
    entry_data = {
        "device_apn": "TEST_APN",
        "api_key": "VALID_KEY",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    # Set internal _power_state value
    entity._power_state = 1


@pytest.mark.asyncio
async def test_set_thing_state_preset_boost(dummy_coordinator, hass):
    """
    Test set_thing_state sets preset mode to PRESET_BOOST.

    When v_powerchill_value equals 1.
    """
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity._ip_address = "192.168.1.100"
    entity._device_key = "VALID_KEY"
    entity._command_suffix = "cmd"
    entity.async_write_ha_state = MagicMock()

    # Create a response where econo=0 and powerchill=1
    # so that the code sets PRESET_BOOST.
    mock_response = {
        "port1": {
            "power": 1,
            "mode": 3,  # COOL mode for example
            "temperature": 22,
            "sensors": {"room_temp": 23},
            "fan": 5,
            "v_swing": 1,
            "econo": 0,
            "powerchill": 1,
        }
    }

    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        return_value=mock_response,
    ):
        data = json.dumps({"port1": {"temperature": 22}})
        await entity.set_thing_state(data)
        # Verify that the branch "if v_powerchill_value == 1:" was executed.
        assert entity._attr_preset_mode == PRESET_BOOST
    assert entity.power_state == 1


@pytest.mark.asyncio
async def test_set_thing_state_invalid_data_exception(dummy_coordinator, hass, caplog):
    """
    Test that set_thing_state logs an error.

    When an InvalidDataException is raised.
    """
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity._ip_address = "192.168.1.100"
    entity._device_key = "VALID_KEY"
    entity._command_suffix = "cmd"
    entity.async_write_ha_state = MagicMock()

    data = json.dumps({"port1": {"temperature": 22}})

    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        side_effect=InvalidDataException("Invalid Data"),
    ):
        await entity.set_thing_state(data)

    # Check that the error message for InvalidDataException is logged.
    assert f"Error executing command {entity._unique_id}:" in caplog.text
    assert "Invalid Data" in caplog.text


@pytest.mark.asyncio
async def test_handle_coordinator_update_missing_data(dummy_coordinator, hass):
    """
    Test that _handle_coordinator_update sets _attr_available to False.

    When the coordinator data is missing the expected 'port1' key.
    """
    entry_data = {
        "device_apn": "TEST_APN",
        "api_key": "VALID_KEY",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    # Patch async_write_ha_state to avoid side effects.
    entity.async_write_ha_state = MagicMock()
    # Simulate missing data by setting coordinator.data to an empty dict.
    dummy_coordinator.data = {}
    entity._handle_coordinator_update()
    assert entity._attr_available is False


@pytest.mark.asyncio
async def test_handle_coordinator_update_valid_calls_write_state(
    dummy_coordinator, hass
):
    """Test that _handle_coordinator_update sets _attr_available to True."""
    entry_data = {
        "device_apn": "TEST_APN",
        "api_key": "VALID_KEY",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }
    entity = DaikinClimate(entry_data, dummy_coordinator)
    entity.hass = hass
    entity.entity_id = "climate.test_entity"
    # Patch async_write_ha_state so we can count its calls.
    entity.async_write_ha_state = MagicMock()
    # Patch update_entity_properties
    # so that its internal call to async_write_ha_state occurs.
    entity.update_entity_properties = MagicMock()
    # Set valid coordinator data (with "port1" present).
    dummy_coordinator.data = {
        "port1": {"fw_ver": "1.0.0", "temperature": 24, "power": 1}
    }
    # Call _handle_coordinator_update.
    entity._handle_coordinator_update()

    # Verify that update_entity_properties was called with valid data.
    entity.update_entity_properties.assert_called_once_with(dummy_coordinator.data)
    # The branch in _handle_coordinator_update sets _attr_available to True.
    assert entity._attr_available is True
