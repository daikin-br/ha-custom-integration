"""Select entities for the Daikin smart AC."""

from __future__ import annotations

from typing import Any

from pyiotdevice import get_fan_mode_value, map_fan_speed

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FAN_MODES
from .coordinator import DaikinConfigEntry, DaikinDataUpdateCoordinator
from .entity import DaikinEntity

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0

DRY_MODE = 2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaikinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Daikin selects from a config entry."""
    async_add_entities([DaikinFanSpeed(entry)])


class DaikinFanSpeed(DaikinEntity, SelectEntity):
    """Fan speed with the same options as the climate entity's fan modes."""

    coordinator: DaikinDataUpdateCoordinator

    _attr_translation_key = "fan_speed"
    # The climate entity stays the primary control, so this starts disabled.
    _attr_entity_registry_enabled_default = False

    def __init__(self, config_entry: DaikinConfigEntry) -> None:
        """Initialize the fan speed select."""
        super().__init__(config_entry.runtime_data)
        device_data = config_entry.data
        # _unique_id identifies the device; the entity gets its own unique id.
        self._unique_id = str(device_data.get("device_apn", ""))
        self._device_name = device_data.get("device_name", "Unknown")
        self._device_info = dict(
            device_data,
            fw_ver=self._port_status.get("fw_ver", "unknown"),
        )
        self._attr_unique_id = f"{self._unique_id}_fan_speed"
        self._attr_options = list(FAN_MODES)

    @property
    def _port_status(self) -> dict[str, Any]:
        """Return the latest status reported by the device."""
        return (self.coordinator.data or {}).get("port1", {})

    @property
    def current_option(self) -> str | None:
        """Return the current fan speed, mapped like the climate entity."""
        if "fan" not in self._port_status:
            return None
        return map_fan_speed(self._port_status["fan"])

    async def async_select_option(self, option: str) -> None:
        """Set the fan speed."""
        if self._port_status.get("mode") == DRY_MODE:
            raise HomeAssistantError("Fan speed cannot be changed in dry mode.")
        if self._port_status.get("powerchill") == 1:
            raise HomeAssistantError(
                "Fan speed cannot be changed while PowerChill is enabled."
            )
        await self.coordinator.async_send_command(fan=get_fan_mode_value(option))
