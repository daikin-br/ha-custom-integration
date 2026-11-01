"""Switch entities for the Daikin smart AC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DaikinConfigEntry, DaikinDataUpdateCoordinator
from .entity import DaikinEntity

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DaikinSwitchEntityDescription(SwitchEntityDescription):
    """Describe a Daikin switch backed by one device field."""

    field: str
    # Only usable while the AC is running.
    requires_power: bool = False
    # Fields that must be turned off together when this switch turns on.
    exclusive_with: tuple[str, ...] = ()
    # Capability flag that must not be 0 for the switch to be created.
    capability: str | None = None


# The climate entity stays the primary control, so these start disabled.
SWITCHES: tuple[DaikinSwitchEntityDescription, ...] = (
    DaikinSwitchEntityDescription(
        key="power",
        translation_key="power",
        field="power",
        entity_registry_enabled_default=False,
    ),
    DaikinSwitchEntityDescription(
        key="powerchill",
        translation_key="powerchill",
        field="powerchill",
        requires_power=True,
        exclusive_with=("econo",),
        entity_registry_enabled_default=False,
    ),
    DaikinSwitchEntityDescription(
        key="econo",
        translation_key="econo",
        field="econo",
        requires_power=True,
        exclusive_with=("powerchill",),
        entity_registry_enabled_default=False,
    ),
    DaikinSwitchEntityDescription(
        key="v_swing",
        translation_key="v_swing",
        field="v_swing",
        capability="v_sw",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaikinConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Daikin switches from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        DaikinSwitch(entry, description)
        for description in SWITCHES
        if description.capability is None
        or coordinator.capabilities.get(description.capability) != 0
    )


class DaikinSwitch(DaikinEntity, SwitchEntity):
    """A Daikin AC feature exposed as a switch."""

    entity_description: DaikinSwitchEntityDescription
    coordinator: DaikinDataUpdateCoordinator

    def __init__(
        self,
        config_entry: DaikinConfigEntry,
        description: DaikinSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(config_entry.runtime_data)
        self.entity_description = description
        device_data = config_entry.data
        # _unique_id identifies the device; the entity gets its own unique id.
        self._unique_id = str(device_data.get("device_apn", ""))
        self._device_name = device_data.get("device_name", "Unknown")
        self._device_info = dict(
            device_data,
            fw_ver=self._port_status.get("fw_ver", "unknown"),
        )
        self._attr_unique_id = f"{self._unique_id}_{description.key}"

    @property
    def _port_status(self) -> dict[str, Any]:
        """Return the latest status reported by the device."""
        return (self.coordinator.data or {}).get("port1", {})

    @property
    def available(self) -> bool:
        """Return True when the device reports this field."""
        return super().available and self.entity_description.field in self._port_status

    @property
    def is_on(self) -> bool:
        """Return True if the feature is on."""
        return self._port_status.get(self.entity_description.field) == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the feature on."""
        description = self.entity_description
        if description.requires_power and self._port_status.get("power") != 1:
            raise HomeAssistantError(
                "This operation cannot be performed because the AC is turned off."
            )
        fields = {description.field: 1}
        for other in description.exclusive_with:
            if self._port_status.get(other) == 1:
                fields[other] = 0
        await self.coordinator.async_send_command(**fields)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the feature off."""
        await self.coordinator.async_send_command(**{self.entity_description.field: 0})
