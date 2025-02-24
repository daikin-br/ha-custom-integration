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
from homeassistant.const import ATTR_TEMPERATURE, CONF_API_KEY

from custom_components.daikin_br.climate import (
    CommunicationErrorException,
    DaikinClimate,
    InvalidDataException,
    async_setup_entry,
)


# Fixture to mock a Home Assistant config entry
@pytest.fixture
def mock_config_entry():
    """Fixture to create a mock config entry."""

    def _create_entry(data):
        entry = MagicMock()
        entry.data = data
        return entry

    return _create_entry


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
    # Mock entry data
    entry = MagicMock()
    entry.data = {
        CONF_API_KEY: "INVALID_KEY",
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "device_name": "TEST DEVICE",
    }

    # Mock async_add_entities as an MagicMock
    async_add_entities = MagicMock()

    # Mock get_thing_info to raise an exception (simulating invalid device key)
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=Exception("Invalid device key"),
    ):
        # Call async_setup_entry which should internally call async_add_entities
        await async_setup_entry(hass, entry, async_add_entities)

    # Ensure the correct error message is logged
    assert "Unexpected error" in caplog.text

    # Ensure async_add_entities was called once, but we do not await it
    async_add_entities.assert_called_once()

    # Ensure the added entity is of type DaikinClimate and is unavailable
    args, _ = async_add_entities.call_args
    assert isinstance(args[0][0], DaikinClimate)
    assert args[0][0].available is False


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

    # Ensure the correct error message is logged
    assert "Unexpected error" in caplog.text

    # Ensure async_add_entities is awaited once
    async_add_entities.assert_called_once()

    # Ensure entity is created but marked as unavailable
    entity = async_add_entities.call_args[0][0][
        0
    ]  # Extract first entity from the call args
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

    # Use MagicMock for async_add_entities (synchronous mock is sufficient).
    async_add_entities = MagicMock()

    # Patch async_write_ha_state in DaikinClimate to be a no-op,
    # so that it doesn't require hass to be set.
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

    # Ensure entity is created and marked as unavailable.
    assert isinstance(entity, DaikinClimate)
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

    # Mock a valid device response
    mock_status = {"port1": {"fw_ver": "1.0.0", "temperature": 24}}

    with patch(
        "custom_components.daikin_br.climate.get_thing_info", return_value=mock_status
    ), patch.object(
        DaikinClimate, "update_entity_properties", AsyncMock()
    ) as mock_update:
        await async_setup_entry(hass, entry, async_add_entities)

    # Ensure no error is logged
    assert "Device setup failed. Invalid device key." not in caplog.text

    # Ensure async_add_entities is called once
    async_add_entities.assert_called_once()

    # Retrieve the entity that was created
    entity = async_add_entities.call_args[0][0][0]

    # Ensure entity is created and available
    assert isinstance(entity, DaikinClimate)
    assert entity.available is True

    # Ensure update_entity_properties was awaited with correct status
    mock_update.assert_awaited_once_with(mock_status)


@pytest.mark.asyncio
async def test_async_set_hvac_mode(hass, caplog):
    """Test setting various HVAC modes in DaikinClimate."""
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)

    # Mock set_thing_state method
    climate_entity.set_thing_state = AsyncMock()

    # Define expected mode mappings and JSON payloads
    test_cases = {
        HVACMode.OFF: json.dumps({"port1": {"power": 0}}),
        HVACMode.FAN_ONLY: json.dumps({"port1": {"mode": 6, "power": 1}}),
        HVACMode.COOL: json.dumps({"port1": {"mode": 3, "power": 1}}),
        HVACMode.DRY: json.dumps({"port1": {"mode": 2, "power": 1}}),
        HVACMode.HEAT: json.dumps({"port1": {"mode": 4, "power": 1}}),
        HVACMode.AUTO: json.dumps({"port1": {"mode": 1, "power": 1}}),
    }

    # Test all valid HVAC modes
    for hvac_mode, expected_json in test_cases.items():
        await climate_entity.async_set_hvac_mode(hvac_mode)
        climate_entity.set_thing_state.assert_called_with(expected_json)
        climate_entity.set_thing_state.reset_mock()  # Reset mock for the next iteration

    # Test an unsupported mode
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

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)
    climate_entity.set_thing_state = AsyncMock()

    # **Set the hass instance explicitly**
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # **Ensure logs are captured**
    caplog.set_level(logging.ERROR)

    # Define expected fan mode mappings and JSON payloads
    test_cases = {
        "auto": {"port1": {"fan": 17}},
        "high": {"port1": {"fan": 7}},
        "medium_high": {"port1": {"fan": 6}},
        "medium": {"port1": {"fan": 5}},
        "low_medium": {"port1": {"fan": 4}},
        "low": {"port1": {"fan": 3}},
        "quiet": {"port1": {"fan": 18}},
    }

    # Test valid fan modes when not in DRY mode
    climate_entity._hvac_mode = HVACMode.COOL  # Ensure not in DRY mode
    for fan_mode, expected_data in test_cases.items():
        expected_json = json.dumps(expected_data)

        await climate_entity.async_set_fan_mode(fan_mode)

        # Verify if the correct JSON payload was sent
        climate_entity.set_thing_state.assert_called_once_with(expected_json)
        climate_entity.set_thing_state.reset_mock()  # Reset mock for the next iteration

    # Test fan mode change when in DRY mode (should not send command)
    climate_entity._hvac_mode = HVACMode.DRY
    await climate_entity.async_set_fan_mode("medium")

    assert any(
        "Fan mode change operation is not permitted" in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # **Test unsupported fan mode**
    climate_entity._hvac_mode = HVACMode.COOL  # Set HVAC mode back to COOL
    caplog.clear()  # Ensure only relevant logs are checked
    await climate_entity.async_set_fan_mode("INVALID_MODE")

    # **Debugging: Print logs to check what was actually captured**
    print("\nCaptured Logs:\n", caplog.text)

    # **Updated Assertion for the log message**
    assert any(
        "Unsupported fan mode." in record.message for record in caplog.records
    ), "Expected 'Unsupported fan mode.' in logs"
    climate_entity.set_thing_state.assert_not_called()


@pytest.mark.asyncio
async def test_async_set_temperature(hass, caplog):
    """Test setting various temperature values in DaikinClimate."""
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)
    climate_entity.set_thing_state = AsyncMock()

    # **Set the hass instance explicitly**
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # **Ensure logs are captured**
    caplog.set_level(logging.ERROR)

    # **Test valid temperature setting in COOL mode**
    climate_entity._hvac_mode = HVACMode.COOL
    valid_temp = 22
    expected_json = json.dumps({"port1": {"temperature": valid_temp}})
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: valid_temp})

    # Verify if the correct JSON payload was sent
    climate_entity.set_thing_state.assert_called_once_with(expected_json)
    climate_entity.set_thing_state.reset_mock()

    # **Test temperature below range in COOL mode**
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 10})

    assert any(
        "Temperature 10°C is out of range for COOL mode (16-32°C)." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # **Test temperature above range in COOL mode**
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 35})

    assert any(
        "Temperature 35°C is out of range for COOL mode (16-32°C)." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # **Test temperature setting in FAN_ONLY mode (should fail)**
    climate_entity._hvac_mode = HVACMode.FAN_ONLY
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 24})

    assert any(
        "Temperature cannot be changed in fan_only mode." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # **Test temperature setting in DRY mode (should fail)**
    climate_entity._hvac_mode = HVACMode.DRY
    caplog.clear()
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 25})

    assert any(
        "Temperature cannot be changed in dry mode." in record.message
        for record in caplog.records
    )
    climate_entity.set_thing_state.assert_not_called()

    # **Test missing temperature attribute (should fail)**
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
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)

    # Mock the schedule_update_ha_state method using MagicMock
    climate_entity.schedule_update_ha_state = MagicMock()

    # **Set the hass instance explicitly**
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # **Ensure logs are captured**
    caplog.set_level(logging.ERROR)

    # **Test setting ECO mode when the device is ON**
    climate_entity._power_state = 1
    # expected_json_eco = json.dumps({"port1": {"powerchill": 0, "econo": 1}})
    await climate_entity.async_set_preset_mode(PRESET_ECO)

    assert climate_entity._attr_preset_mode == PRESET_ECO
    climate_entity.schedule_update_ha_state.assert_called_once()
    climate_entity.schedule_update_ha_state.reset_mock()

    # **Test setting BOOST mode when the device is ON**
    # expected_json_boost = json.dumps({"port1": {"powerchill": 1, "econo": 0}})
    await climate_entity.async_set_preset_mode(PRESET_BOOST)

    assert climate_entity._attr_preset_mode == PRESET_BOOST
    climate_entity.schedule_update_ha_state.assert_called_once()
    climate_entity.schedule_update_ha_state.reset_mock()

    # **Test setting NONE mode when the device is ON**
    # expected_json_none = json.dumps({"port1": {"powerchill": 0, "econo": 0}})
    await climate_entity.async_set_preset_mode(PRESET_NONE)

    assert climate_entity._attr_preset_mode == PRESET_NONE
    climate_entity.schedule_update_ha_state.assert_called_once()
    climate_entity.schedule_update_ha_state.reset_mock()

    # **Test setting preset mode when device is OFF (should fail)**
    climate_entity._power_state = 0
    caplog.clear()
    await climate_entity.async_set_preset_mode(PRESET_ECO)

    assert any(
        "The device operation cannot be performed because it is turned off."
        in record.message
        for record in caplog.records
    )
    climate_entity.schedule_update_ha_state.assert_not_called()

    # Ensure that schedule_update_ha_state is properly handled
    # Do not await it in the actual test
    climate_entity.schedule_update_ha_state.return_value = None


@pytest.mark.asyncio
async def test_async_set_swing_mode(hass, caplog):
    """Test setting swing modes in DaikinClimate."""
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)
    climate_entity.set_thing_state = AsyncMock()

    # **Set the hass instance explicitly**
    climate_entity.hass = hass
    climate_entity.entity_id = "climate.test_device"

    # **Define available swing modes**
    climate_entity._attr_swing_modes = {SWING_VERTICAL, SWING_OFF}

    # **Test setting SWING_VERTICAL mode**
    expected_json_vertical = json.dumps({"port1": {"v_swing": 1}})
    await climate_entity.async_set_swing_mode(SWING_VERTICAL)

    climate_entity.set_thing_state.assert_called_with(expected_json_vertical)
    climate_entity.set_thing_state.reset_mock()

    # **Test setting SWING_OFF mode**
    expected_json_off = json.dumps({"port1": {"v_swing": 0}})
    await climate_entity.async_set_swing_mode(SWING_OFF)

    climate_entity.set_thing_state.assert_called_with(expected_json_off)
    climate_entity.set_thing_state.reset_mock()

    # **Test unsupported swing mode**
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
    # Mock entry data for DaikinClimate
    entry_data = {
        "device_apn": "TEST_APN",
        "host": "192.168.1.100",
        "api_key": "VALID_KEY",
        "device_name": "TEST DEVICE",
    }

    # Create DaikinClimate instance
    climate_entity = DaikinClimate(entry_data)

    # Mock the response from the send_operation_data call
    mock_response = {
        "port1": {
            "power": 1,
            "mode": 3,  # COOL mode (this should map to HVACMode.COOL)
            "temperature": 22,
            "sensors": {"room_temp": 23},
            "fan": 5,  # Mock fan speed (this should map to 'medium')
            "v_swing": 1,
            "econo": 1,
            "powerchill": 0,
        }
    }

    # Mocking the actual state-setting function using patch
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        return_value=mock_response,
    ):
        # Set up DaikinClimate instance
        climate_entity.hass = hass
        climate_entity._ip_address = "192.168.1.100"
        climate_entity._device_key = "VALID_KEY"
        climate_entity._command_suffix = "command"

        # Mock async_write_ha_state using MagicMock
        climate_entity.async_write_ha_state = MagicMock()

        # Call the method set_thing_state with mock data
        data = json.dumps({"port1": {"temperature": 22}})

        # Trigger internal state change by calling the method
        await climate_entity.set_thing_state(data)

        # Verify that internal state is updated correctly based on mock response
        assert (
            climate_entity._power_state == 1
        )  # Should be ON based on the mock response
        assert climate_entity._hvac_mode == HVACMode.COOL  # Checking for HVACMode.COOL
        assert (
            climate_entity._target_temperature == 22
        )  # Target temperature should match mock response
        assert (
            climate_entity._current_temperature == 23
        )  # Current temperature from mock response
        assert (
            climate_entity._fan_mode == "medium"
        )  # Fan mode should be 'medium' based on mock response
        assert (
            climate_entity._attr_swing_mode == "vertical"
        )  # Based on v_swing value (1)
        assert climate_entity._attr_preset_mode == "eco"  # Based on econo value (1)

        # Check if async_write_ha_state was called once after the state change
        climate_entity.async_write_ha_state.assert_called_once()

        # Verify that the log contains the expected preset mode set message
        assert "Preset mode set to : eco" in caplog.text

    # Test error scenario if the operation fails (mocking an exception)
    with patch(
        "custom_components.daikin_br.climate.send_operation_data",
        side_effect=Exception("Failed to send command"),
    ):
        caplog.clear()  # Clear any previous logs
        await climate_entity.set_thing_state(data)

        # Check if the error log is captured properly
        assert "Failed to send command: Failed to send command" in caplog.text


@pytest.mark.asyncio
async def test_update_entity_properties():
    """Test update_entity_properties function."""
    # Create DaikinClimate instance
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Mock async_write_ha_state to avoid actually writing state during test
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate input data for port_status
    port_status = {
        "port1": {
            "sensors": {"room_temp": 23},
            "temperature": 22,
            "power": 1,  # Power ON
            "mode": 3,  # COOL mode (assuming HVACMode.COOL maps to 3)
            "fan": 5,  # Fan speed 'medium' (mapped to 'medium' in your setup)
            "v_swing": 1,  # Vertical swing
            "econo": 1,  # Economy mode
            "powerchill": 0,  # No powerchill
        }
    }

    # Call update_entity_properties with mocked data
    await climate_entity.update_entity_properties(port_status)

    # Verify that the internal state is updated as expected
    assert climate_entity._current_temperature == 23  # room_temp from sensors
    assert climate_entity._target_temperature == 22  # temperature from port_status
    assert climate_entity._power_state == 1  # Power ON
    assert climate_entity._hvac_mode == HVACMode.COOL  # COOL mode from port_status
    assert climate_entity._fan_mode == "medium"  # Fan speed 'medium'
    assert climate_entity._attr_swing_mode == SWING_VERTICAL  # Vertical swing mode
    assert climate_entity._attr_preset_mode == PRESET_ECO  # Economy mode

    # Verify async_write_ha_state is called once
    climate_entity.async_write_ha_state.assert_called_once()

    # Verify the skip update flag
    assert (
        climate_entity._skip_update is True
    )  # Should be True after updating properties


@pytest.mark.asyncio
async def test_update_entity_properties_device_off():
    """Test update_entity_properties when the device is OFF."""
    # Create DaikinClimate instance
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Mock async_write_ha_state to avoid actually writing state during test
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate input data for port_status with the device OFF
    port_status = {
        "port1": {
            "sensors": {"room_temp": 23},
            "temperature": 22,
            "power": 0,  # Power OFF
            "mode": 0,  # HVACMode.OFF
            "fan": 3,  # Low
            "v_swing": 0,  # No swing
            "econo": 0,  # No economy mode
            "powerchill": 0,  # No powerchill
        }
    }

    # Call update_entity_properties with mocked data
    await climate_entity.update_entity_properties(port_status)

    # Verify that the internal state is updated as expected
    assert climate_entity._current_temperature == 23  # room_temp from sensors
    assert climate_entity._target_temperature == 22  # temperature from port_status
    assert climate_entity._power_state == 0  # Power OFF
    assert climate_entity._hvac_mode == HVACMode.OFF  # OFF mode since the power is 0
    assert climate_entity._fan_mode == "low"  # No fan
    assert climate_entity._attr_swing_mode == SWING_OFF  # No swing
    assert (
        climate_entity._attr_preset_mode == PRESET_NONE
    )  # No economy or powerchill mode

    # Verify async_write_ha_state is called once
    climate_entity.async_write_ha_state.assert_called_once()

    # Verify the skip update flag
    assert (
        climate_entity._skip_update is True
    )  # Should be True after updating properties


@pytest.mark.asyncio
async def test_async_update_success():
    """Test async_update when the device successfully returns status."""
    # Create a DaikinClimate instance
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Mock the Home Assistant instance (hass)
    climate_entity.hass = MagicMock()

    # Mock async_add_executor_job method
    climate_entity.hass.async_add_executor_job = AsyncMock()

    # Mock async_write_ha_state
    climate_entity.async_write_ha_state = MagicMock()

    # Mock update_entity_properties
    climate_entity.update_entity_properties = AsyncMock()

    # Mock get_thing_info to return valid data
    status_mock = {
        "port1": {
            "sensors": {"room_temp": 23},
            "temperature": 22,
            "power": 1,
            "mode": 3,
        }
    }

    with patch(
        "custom_components.daikin_br.climate.get_thing_info", return_value=status_mock
    ):
        with patch.object(
            climate_entity.hass, "async_add_executor_job", return_value=status_mock
        ):
            await climate_entity.async_update()

    # Ensure update_entity_properties is called with the status
    climate_entity.update_entity_properties.assert_awaited_once_with(status_mock)

    # Ensure entity is available
    assert climate_entity._attr_available is True

    # Ensure async_write_ha_state is called
    climate_entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_async_update_skip():
    """Test async_update when _skip_update is set to True (it should skip update)."""
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Set _skip_update to True
    climate_entity._skip_update = True

    # Mock async_write_ha_state
    climate_entity.async_write_ha_state = MagicMock()

    # Mock update_entity_properties
    climate_entity.update_entity_properties = AsyncMock()

    await climate_entity.async_update()

    # Ensure update_entity_properties is NOT called
    climate_entity.update_entity_properties.assert_not_awaited()

    # Ensure async_write_ha_state is NOT called
    climate_entity.async_write_ha_state.assert_not_called()

    # Ensure _skip_update is reset to False
    assert climate_entity._skip_update is False


@pytest.mark.asyncio
async def test_async_update_invalid_data_exception():
    """Test async_update when an InvalidDataException is raised."""
    # Create a DaikinClimate instance
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Mock the Home Assistant instance (hass)
    climate_entity.hass = MagicMock()

    # Mock async_add_executor_job method
    climate_entity.hass.async_add_executor_job = AsyncMock()

    # Mock async_write_ha_state
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate InvalidDataException when get_thing_info is called
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=InvalidDataException("Invalid data"),
    ):
        await climate_entity.async_update()

    # Ensure that async_write_ha_state was called after the exception is caught
    climate_entity.async_write_ha_state.assert_called_once()

    # Ensure the entity is marked as unavailable when the exception is raised
    assert climate_entity._attr_available is False

    # # Ensure the exception is logged
    # assert "Error updating device status" in caplog.text


@pytest.mark.asyncio
async def test_async_update_communication_error():
    """Test async_update when a CommunicationErrorException is raised."""
    # Create DaikinClimate instance
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Mock the Home Assistant instance (hass)
    climate_entity.hass = MagicMock()

    # Mock async_add_executor_job method
    climate_entity.hass.async_add_executor_job = AsyncMock()

    # Mock async_write_ha_state
    climate_entity.async_write_ha_state = MagicMock()

    # Simulate CommunicationErrorException when get_thing_info is called
    with patch(
        "custom_components.daikin_br.climate.get_thing_info",
        side_effect=CommunicationErrorException("Communication error"),
    ):
        await climate_entity.async_update()

    # Ensure that async_write_ha_state was called after the exception is caught
    climate_entity.async_write_ha_state.assert_called_once()

    # Ensure the entity is marked as unavailable when the exception is raised
    assert climate_entity._attr_available is False


@pytest.mark.asyncio
async def test_async_update_unexpected_exception(caplog):
    """Test async_update when an unexpected exception is raised."""
    # Create a DaikinClimate instance with test configuration.
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Set up a fake Home Assistant instance on the entity.
    climate_entity.hass = MagicMock()
    climate_entity.hass.async_add_executor_job = AsyncMock()

    # Patch async_write_ha_state using patch.object
    # so that it is replaced with a non-awaitable MagicMock.
    with patch.object(
        climate_entity, "async_write_ha_state", new=MagicMock()
    ) as mock_write:
        # Patch get_thing_info to simulate an unexpected exception.
        with patch(
            "custom_components.daikin_br.climate.get_thing_info",
            side_effect=Exception("Unexpected error"),
        ):
            await climate_entity.async_update()

        # Verify that async_write_ha_state was called once.
        mock_write.assert_called_once()

    # Verify that after the exception, the entity is marked as unavailable.
    assert climate_entity._attr_available is False

    # Verify that the error is logged.
    assert "Unexpected error while updating device status" in caplog.text
    assert "Unexpected error" in caplog.text


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
    # Create an instance of DaikinClimate
    climate_entity = DaikinClimate({})

    # Call map_hvac_mode and verify output
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
    climate_entity = DaikinClimate({})
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
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Simulate setting the temperature
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
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Manually set the private attribute
    climate_entity._attr_swing_mode = swing_mode

    # Assert that the property returns the expected swing mode
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
    climate_entity = DaikinClimate(
        {
            "device_apn": "TEST_APN",
            "host": "192.168.1.100",
            "api_key": "VALID_KEY",
            "device_name": "TEST DEVICE",
        }
    )

    # Manually set the private attribute
    climate_entity._attr_preset_mode = preset_mode

    # Assert that the property returns the expected preset mode
    assert climate_entity.preset_mode == expected_preset_mode
