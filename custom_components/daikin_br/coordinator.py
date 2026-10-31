"""Coordinator for updating Daikin smart AC data."""

from __future__ import annotations

import json
import logging
from typing import Any

from pyiotdevice import (
    CommunicationErrorException,
    InvalidDataException,
    async_send_operation_data,
    prepare_device_payload,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type DaikinConfigEntry = ConfigEntry[DaikinDataUpdateCoordinator]


# pylint: disable=too-many-arguments, too-many-positional-arguments
# pylint: disable=too-few-public-methods
class DaikinDataUpdateCoordinator(DataUpdateCoordinator):
    """DataUpdateCoordinator for Daikin devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: DaikinConfigEntry,
        device_apn,
        update_method,
        update_interval,
    ) -> None:
        """Initialize the coordinator."""
        self.device_apn = device_apn
        self._update_method = update_method
        # Device capability flags from the /device endpoint, e.g. {"heat": 0, "v_sw": 1}.
        self.capabilities: dict[str, Any] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        """Fetch data from the device."""
        try:
            data = await self._update_method()
            if not isinstance(data, dict):
                _LOGGER.debug(
                    "Unable to retrieve device status data for %s", self.device_apn
                )
                _raise_device_data_failure(self.device_apn)
        except Exception as e:
            _LOGGER.debug("Error fetching data for %s: %s", self.device_apn, e)
            raise UpdateFailed(
                f"The device {self.device_apn} is unavailable: {e}"
            ) from e
        else:
            return data

    async def async_send_command(self, **fields: Any) -> None:
        """Send a command to the device and publish the state it returns."""
        entry_data = self.config_entry.data
        try:
            response = await async_send_operation_data(
                entry_data.get("host"),
                entry_data.get(CONF_API_KEY),
                json.dumps(prepare_device_payload(**fields)),
                entry_data.get("command_suffix"),
            )
        except (InvalidDataException, CommunicationErrorException) as e:
            raise HomeAssistantError(
                f"Error sending command to {self.device_apn}: {e}"
            ) from e
        if not isinstance(response, dict) or not response.get("port1"):
            raise HomeAssistantError(
                f"The device {self.device_apn} did not accept the command {fields}"
            )
        self.async_set_updated_data(response)


def _raise_device_data_failure(device_apn: str) -> None:
    """Raise a TypeError to indicate that device data retrieval has failed.

    Args:
        device_apn (str): The device APN for which data retrieval failed.

    Raises:
        TypeError: Always raised to indicate that the device data could not be retrieved.

    """
    raise TypeError("Failed to retrieve device data")
