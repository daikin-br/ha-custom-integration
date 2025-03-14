"""Coordinator for updating Daikin smart AC data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from typing_extensions import TypeAlias

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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
                raise TypeError("Failed to retrieve device data")
            return data
        except Exception as e:
            _LOGGER.debug("Error fetching data for %s: %s", self.device_apn, e)
            raise UpdateFailed(
                f"The device {self.device_apn} is unavailable: {e}"
            ) from e


if TYPE_CHECKING:
    DaikinConfigEntry: TypeAlias = ConfigEntry[DaikinDataUpdateCoordinator]
else:
    DaikinConfigEntry = ConfigEntry
