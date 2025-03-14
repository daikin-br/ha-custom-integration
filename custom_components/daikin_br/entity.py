"""Base entity module for Daikin smart AC."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaikinDataUpdateCoordinator


# pylint: disable=too-few-public-methods
class DaikinEntity(CoordinatorEntity[DaikinDataUpdateCoordinator]):
    """Base entity for Daikin devices using a DataUpdateCoordinator."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            name=self._device_name,
            manufacturer="Daikin",
            model="Smart AC Series",
            sw_version=self._device_info.get("fw_ver"),
        )
