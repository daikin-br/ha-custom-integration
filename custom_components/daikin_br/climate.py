"""Entity feature for the Daikin smart AC."""

from __future__ import annotations

import datetime
import json
import logging

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    SWING_OFF,
    SWING_VERTICAL,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_API_KEY, UnitOfTemperature

# from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from pyiotdevice import (
    CommunicationErrorException,
    InvalidDataException,
    get_thing_info,
    send_operation_data,
)

from .const import DOMAIN, POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Daikin Climate device from a config entry."""
    # Check if the device_key exists in the entry data
    device_key = entry.data.get(CONF_API_KEY)
    # device_apn = entry.data.get("device_apn")
    if not device_key:
        _LOGGER.error("Device key is missing in the configuration entry!")
        return

    # Offload the blocking call to a thread pool
    ip_address = entry.data.get("host")
    # Default firmware version
    entry_data = {**entry.data, "fw_ver": "Unknown"}
    # Track status to avoid calling update on failure
    status = None
    port_status = None

    try:
        status = await hass.async_add_executor_job(
            get_thing_info, ip_address, device_key, "acstatus"
        )

        port_status = status.get("port1", {})
        if not port_status:
            _LOGGER.error("Device setup failed. Invalid device key.")
            raise ValueError("Invalid device key: No port_status")

        # Update firmware version if successful
        entry_data["fw_ver"] = port_status.get("fw_ver", "Unknown")

    except (ValueError, KeyError) as e:
        _LOGGER.error("Configuration error: %s", e)

    except TimeoutError as e:
        _LOGGER.error("Timeout while communicating with the device: %s", e)

    except OSError as e:
        _LOGGER.error("Network error while communicating with the device: %s", e)

    except Exception as e:
        # Logs full traceback
        _LOGGER.exception("Unexpected error: %s", e)

    # Create the entity (always)
    climate_entity = DaikinClimate(entry_data)

    # Mark entity as unavailable if the port status retrieval failed
    if not port_status:
        climate_entity._attr_available = False

    # Add the entity
    async_add_entities([climate_entity])

    # If port status retrieval was successful, update entity properties
    if port_status:
        await climate_entity.update_entity_properties(status)


class DaikinClimate(ClimateEntity):
    """Representation of an Daikin Climate device."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, device_data):
        """Initialize the climate device."""
        self._attr_available = True
        self._remove_listener = None

        self._device_key = device_data.get(CONF_API_KEY, None)
        if self._device_key is None:
            _LOGGER.error("Device key not found while creating entity!")
            return

        _LOGGER.debug(
            "Initializing DaikinClimate - Name: %s, APN: %s",
            device_data.get("device_name"),
            device_data.get("device_apn"),
        )

        self._device_name = device_data.get("device_name", "Unknown")
        self._host = device_data.get("host", None)
        # self._ip_address = f"{device_data.get("device_apn")}.local"
        self._ip_address = self._host
        self._poll_interval = device_data.get("poll_interval")  # For future use
        self._command_suffix = device_data.get("command_suffix")

        self._device_info = device_data
        self._unique_id = device_data.get("device_apn")

        self._power_state = 0  # default is Off
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._hvac_mode = HVACMode.OFF
        self._power_state = 0  # default is Off
        self._target_temperature = None
        self._current_temperature = None
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.PRESET_MODE
        )

        # Define fan modes here, this could depend on the device's capabilities
        self._fan_modes = [
            "auto",
            "high",
            "medium_high",
            "medium",
            "low_medium",
            "low",
            "quiet",
        ]
        self._fan_mode = "auto"  # Default fan mode
        self._attr_preset_modes = [PRESET_NONE, PRESET_ECO, PRESET_BOOST]
        self._attr_preset_mode = PRESET_NONE
        self._attr_swing_modes = [SWING_OFF, SWING_VERTICAL]
        self._attr_swing_mode = SWING_OFF
        # Flag to skip updates
        self._skip_update = False

    @property
    def translation_key(self):
        """Return translation key climate entity."""
        return "daikin_ac"

    @property
    def unique_id(self):
        """Return a unique ID for the climate entity."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the device."""
        # Let the device registry supply the name, so return None here.
        return None

    @property
    def power_state(self):
        """Return the power state."""
        return self._power_state

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._unique_id)},
            "name": self._device_name,
            "manufacturer": "Daikin",
            "model": "Smart AC Series",
            "sw_version": self._device_info.get("fw_ver"),
        }

    @property
    def hvac_modes(self):
        """Return the list of supported HVAC modes."""
        return [
            HVACMode.OFF,
            HVACMode.FAN_ONLY,
            HVACMode.COOL,
            HVACMode.DRY,
            HVACMode.HEAT,
            HVACMode.AUTO,
        ]

    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        return self._hvac_mode

    @property
    def supported_features(self):
        """Return supported features."""
        return self._attr_supported_features

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._current_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temperature

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def fan_modes(self):
        """Return the list of available fan modes."""
        return self._fan_modes

    @property
    def fan_mode(self):
        """Return the current fan mode."""
        return self._fan_mode

    @property
    def preset_modes(self):
        """Return the list of available preset modes."""
        return self._attr_preset_modes

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        return self._attr_preset_mode

    @property
    def swing_modes(self):
        """Return the list of supported swing modes."""
        return self._attr_swing_modes

    @property
    def swing_mode(self):
        """Return the current swing mode."""
        return self._attr_swing_mode

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return 10.0  # Set to the device's minimum temperature

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return 32.0  # Set to the device's maximum temperature

    @property
    def target_temperature_step(self) -> float:
        """Return the supported step size for target temperature."""
        return 1.0  # Set the step size to 1 degree

    def map_hvac_mode(self, hvac_value):
        """Map device HVAC mode value to Home Assistant HVAC modes."""
        hvac_mapping = {
            0: HVACMode.OFF,
            6: HVACMode.FAN_ONLY,
            3: HVACMode.COOL,
            2: HVACMode.DRY,
            4: HVACMode.HEAT,
            1: HVACMode.AUTO,
        }
        return hvac_mapping.get(
            hvac_value, HVACMode.OFF
        )  # Default to HVAC_MODE_OFF if value is unknown

    def map_fan_speed(self, fan_value):
        """Map device fan speed value to Home Assistant fan modes."""
        fan_mapping = {
            17: "auto",
            7: "high",
            6: "medium_high",
            5: "medium",
            4: "low_medium",
            3: "low",
            18: "quiet",
        }
        return fan_mapping.get(
            fan_value, "auto"
        )  # Default to "auto" if value is unknown

    async def async_set_hvac_mode(self, hvac_mode):
        """Set the HVAC mode on the AC device."""
        # Map Home Assistant HVAC modes to device modes
        hvac_mode_mapping = {
            HVACMode.OFF: 0,
            HVACMode.FAN_ONLY: 6,
            HVACMode.COOL: 3,
            HVACMode.DRY: 2,
            HVACMode.HEAT: 4,
            HVACMode.AUTO: 1,
        }

        # Get the corresponding mode value
        mode_value = hvac_mode_mapping.get(hvac_mode)

        if mode_value is None:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            return

        if mode_value == 0:
            data = {"port1": {"power": 0}}
        else:
            # Prepare the payload for the device
            data = {"port1": {"mode": mode_value, "power": 1}}

        # Serialize the payload to JSON
        json_data = json.dumps(data)

        # Use the common function to send the data and update state
        await self.set_thing_state(json_data)

    async def async_set_fan_mode(self, fan_mode):
        """Set the fan mode on the AC device."""
        # Map Home Assistant fan modes to device fan modes
        fan_mode_mapping = {
            "auto": 17,
            "high": 7,
            "medium_high": 6,
            "medium": 5,
            "low_medium": 4,
            "low": 3,
            "quiet": 18,
        }

        # Store the previous fan mode value
        # previous_fan_mode = self._fan_mode

        # Fan speed cannot be changed in DRY MODE
        if self._hvac_mode == HVACMode.DRY:
            message = (
                f"Fan mode change operation is not permitted in {self._hvac_mode} mode."
            )
            _LOGGER.error("Entity %s: %s", self.entity_id, message)
            self.async_write_ha_state()
            return

        # Get the corresponding fan mode value
        fan_mode_value = fan_mode_mapping.get(fan_mode)

        if fan_mode_value is None:
            _LOGGER.error("Unsupported fan mode.")
            return

        # Prepare the payload for the device
        data = {"port1": {"fan": fan_mode_value}}

        # Serialize the payload to JSON
        json_data = json.dumps(data)

        # Use the common function to send the data and update state
        await self.set_thing_state(json_data)

    async def async_set_temperature(self, **kwargs):
        """Set the target temperature on the AC device."""
        # Get the temperature value from kwargs
        temperature = kwargs.get(ATTR_TEMPERATURE)

        if temperature is None:
            message = "Temperature not provided in the request."
            _LOGGER.error("Entity %s: %s", self.entity_id, message)
            return

        # Check HVAC mode and apply temperature range or restrictions
        if self._hvac_mode == HVACMode.COOL:
            if temperature < 16 or temperature > 32:
                message = (
                    "Temperature %s°C is out of range for COOL mode (16-32°C)."
                    % temperature
                )
                _LOGGER.error("Entity %s: %s", self.entity_id, message)
                # Revert the temperature dial to the previous value
                self._target_temperature = temperature
                self.async_write_ha_state()
                return
        elif self._hvac_mode in [HVACMode.FAN_ONLY, HVACMode.DRY]:
            message = f"Temperature cannot be changed in {self._hvac_mode} mode."
            _LOGGER.error("Entity %s: %s", self.entity_id, message)
            # Revert the temperature dial to the previous value
            self._target_temperature = temperature
            self.async_write_ha_state()
            return

        # Prepare the payload for the device
        data = {"port1": {"temperature": temperature}}

        # Serialize the payload to JSON
        json_data = json.dumps(data)

        # Use the common function to send the data and update state
        await self.set_thing_state(json_data)

    async def async_set_preset_mode(self, preset_mode):
        """Set the preset mode only if device is on (power_state = 1)."""
        data = None
        if self._power_state == 1:  # Check if the device is ON
            if preset_mode == PRESET_ECO:
                # Prepare the payload for the device
                data = {"port1": {"powerchill": 0, "econo": 1}}
                self._attr_preset_mode = PRESET_ECO
                self.schedule_update_ha_state()
            elif preset_mode == PRESET_BOOST:
                # Prepare the payload for the device
                data = {"port1": {"powerchill": 1, "econo": 0}}
                self._attr_preset_mode = PRESET_BOOST
                self.schedule_update_ha_state()
            elif preset_mode == PRESET_NONE:
                # Prepare the payload for the device
                data = {"port1": {"powerchill": 0, "econo": 0}}
                self._attr_preset_mode = PRESET_NONE
                self.schedule_update_ha_state()
        else:
            # Send a persistent notification when the device is off
            message = (
                "The device operation cannot be performed because it is turned off."
            )
            _LOGGER.error("Entity %s: %s", self.entity_id, message)
            self.async_write_ha_state()
            return

        if data is None:
            _LOGGER.error(
                "Entity %s: Unsupported preset mode: %s", self.entity_id, preset_mode
            )
            return

        # Serialize the payload to JSON
        json_data = json.dumps(data)

        # Use the common function to send the data and update state
        await self.set_thing_state(json_data)

    async def async_set_swing_mode(self, swing_mode):
        """Set the vertical swing mode on the device."""
        if swing_mode not in self._attr_swing_modes:
            _LOGGER.error("Unsupported swing mode: %s", swing_mode)
            return

        v_swing_value = None

        # Map the swing mode to the device-specific value
        if swing_mode == SWING_VERTICAL:  # "vertical":
            v_swing_value = 1
        elif swing_mode == SWING_OFF:  # "none":
            v_swing_value = 0

        # Prepare the payload
        data = {"port1": {"v_swing": v_swing_value}}

        # Serialize the payload to JSON
        json_data = json.dumps(data)

        # Send the updated swing mode to the device
        await self.set_thing_state(json_data)

    async def set_thing_state(self, data):
        """Send data and update internal state based on the response."""
        try:
            _LOGGER.debug("send command request: %s", data)
            # Send command using send_operation_data and await the response
            response = await self.hass.async_add_executor_job(
                send_operation_data,
                self._ip_address,
                self._device_key,
                data,
                self._command_suffix,
            )
            _LOGGER.debug("send command response: %s", response)

            # Update internal state based on the response
            port_status = response.get("port1", {})
            self._power_state = port_status.get("power")
            mode_value = port_status.get("mode")
            self._hvac_mode = (
                self.map_hvac_mode(mode_value) if self._power_state else HVACMode.OFF
            )
            self._target_temperature = port_status.get("temperature")
            self._current_temperature = port_status.get("sensors", {}).get("room_temp")
            self._fan_mode = self.map_fan_speed(port_status.get("fan"))
            # Update vertical swing state
            v_swing_value = port_status.get("v_swing", 0)  # Default to 0 if not present
            self._attr_swing_mode = SWING_VERTICAL if v_swing_value == 1 else SWING_OFF

            # Update the presets state
            v_econo_value = port_status.get("econo", 0)
            v_powerchill_value = port_status.get("powerchill", 0)
            if v_econo_value == 1:
                self._attr_preset_mode = PRESET_ECO

            if v_powerchill_value == 1:
                self._attr_preset_mode = PRESET_BOOST

            if v_econo_value == 0 and v_powerchill_value == 0:
                self._attr_preset_mode = PRESET_NONE

            _LOGGER.debug("Preset mode set to : %s", self._attr_preset_mode)

            # Update other properties if needed
            self.async_write_ha_state()

            # Skip update as we already know the new state
            self._skip_update = True

        except (InvalidDataException, CommunicationErrorException) as e:
            _LOGGER.error("Error executing command %s: %s", self._unique_id, e)

        except Exception as e:
            _LOGGER.error("Failed to send command: %s", e)

    async def update_entity_properties(self, status):
        """Asynchronously update entity properties based on the received status."""
        port_status = status.get("port1", {})

        self._current_temperature = port_status.get("sensors", {}).get("room_temp")
        self._target_temperature = port_status.get("temperature")

        # Map power state to HVAC mode
        self._power_state = port_status.get("power", 0)  # 0 = OFF, 1 = ON
        if self._power_state == 0:
            self._hvac_mode = HVACMode.OFF
        else:
            mode_value = port_status.get("mode", 0)  # Default to 0 if not present
            self._hvac_mode = self.map_hvac_mode(mode_value)

        # Update fan mode
        self._fan_mode = self.map_fan_speed(port_status.get("fan"))

        # Update vertical swing state
        v_swing_value = port_status.get("v_swing", 0)  # Default to 0 if not present
        self._attr_swing_mode = SWING_VERTICAL if v_swing_value == 1 else SWING_OFF

        # Update preset mode based on economy and power chill settings
        v_econo_value = port_status.get("econo", 0)
        v_powerchill_value = port_status.get("powerchill", 0)

        if v_econo_value == 1:
            self._attr_preset_mode = PRESET_ECO
        elif v_powerchill_value == 1:
            self._attr_preset_mode = PRESET_BOOST
        else:
            self._attr_preset_mode = PRESET_NONE

        # Write updated state asynchronously
        self.async_write_ha_state()

        # Skip this update cycle
        self._skip_update = True

    async def async_update(self, _=None):
        """Fetch new state data for the entity."""
        if self._skip_update:
            # Skip this update cycle
            self._skip_update = False
            return

        try:
            # Offload the blocking call to a thread pool
            status = await self.hass.async_add_executor_job(
                get_thing_info, self._ip_address, self._device_key, "acstatus"
            )

            # Update entity properties with the latest device state
            _LOGGER.debug(
                "Updating entity properties - Name: %s, APN: %s",
                self._device_name,
                self._unique_id,
            )
            await self.update_entity_properties(status)
            self._attr_available = True

        except (InvalidDataException, CommunicationErrorException) as e:
            _LOGGER.error("Error updating device status for %s, %s", self._unique_id, e)
            self._attr_available = False
        except Exception as e:
            _LOGGER.error(
                "Unexpected error while updating device status for %s, %s",
                self._unique_id,
                e,
            )
            self._attr_available = False
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Register update interval when entity is added to HA."""
        _LOGGER.debug("Registering periodic polling every %s seconds", POLL_INTERVAL)
        self._remove_listener = async_track_time_interval(
            self.hass, self.async_update, datetime.timedelta(seconds=POLL_INTERVAL)
        )

    async def async_will_remove_from_hass(self):
        """Cancel the update interval when entity is removed from HA."""
        if hasattr(self, "_remove_listener") and self._remove_listener:
            _LOGGER.debug("Removing update listener")
            # Cancel the scheduled update
            self._remove_listener()
            self._remove_listener = None
