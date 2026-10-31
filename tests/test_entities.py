"""End-to-end tests of the climate, switch and select entities sharing one device."""

import json
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_br.const import DOMAIN, FAN_MODES
from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODES,
    ATTR_PRESET_MODE,
    ATTR_SWING_MODE,
    PRESET_BOOST,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES, CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

APN = "TEST_APN"


class FakeDevice:
    """Simulate the AC: keep its state and answer like the firmware."""

    def __init__(self) -> None:
        """Start cooling, with no preset."""
        self.port = {
            "power": 1,
            "mode": 3,
            "temperature": 24,
            "sensors": {"room_temp": 26},
            "fan": 17,
            "v_swing": 0,
            "econo": 0,
            "powerchill": 0,
            "fw_ver": "p1.0.4.2",
        }
        self.capabilities: dict | Exception | None = {"heat": 1, "v_sw": 1}
        self.sent: list[dict] = []

    async def get_info(self, host, key, endpoint):
        """Answer /acstatus and /device."""
        if endpoint == "device":
            if isinstance(self.capabilities, Exception):
                raise self.capabilities
            return self.capabilities
        return {"port1": json.loads(json.dumps(self.port))}

    async def send(self, host, key, data, suffix):
        """Apply a command; the firmware keeps Econo and Power Chill exclusive."""
        fields = json.loads(data)["port1"]
        self.sent.append(fields)
        self.port.update(fields)
        if fields.get("powerchill") == 1:
            self.port["econo"] = 0
        if fields.get("econo") == 1:
            self.port["powerchill"] = 0
        return {"port1": json.loads(json.dumps(self.port))}


# pylint: disable=redefined-outer-name
@pytest.fixture
def device(mock_async_zeroconf):
    """Patch the device API with a simulated AC."""
    fake = FakeDevice()
    with (
        patch("custom_components.daikin_br.async_get_thing_info", new=fake.get_info),
        patch(
            "custom_components.daikin_br.climate.async_send_operation_data",
            new=fake.send,
        ),
        patch(
            "custom_components.daikin_br.coordinator.async_send_operation_data",
            new=fake.send,
        ),
    ):
        yield fake


async def _setup(hass: HomeAssistant, enable: tuple[str, ...] = ()) -> MockConfigEntry:
    """Set up the integration, enabling the given (platform, key) entities first."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=APN,
        data={
            CONF_API_KEY: "VALID_KEY",
            "host": "192.168.1.100",
            "device_apn": APN,
            "device_name": "Sala",
            "command_suffix": "BZ",
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for platform, key in enable:
        # Pre-register the entity as enabled, like a user enabling it in the UI.
        registry.async_get_or_create(
            platform, DOMAIN, f"{APN}_{key}", config_entry=entry
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Load the device state into the entities.
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


ALL_EXTRAS = (
    ("switch", "power"),
    ("switch", "powerchill"),
    ("switch", "econo"),
    ("switch", "v_swing"),
    ("select", "fan_speed"),
)


@pytest.mark.asyncio
async def test_new_entities_disabled_by_default(hass: HomeAssistant, device) -> None:
    """Existing installations keep the same climate entity; extras start disabled."""
    await _setup(hass)
    registry = er.async_get(hass)

    climate = registry.async_get(_entity_id(hass, "climate", APN))
    assert climate.disabled_by is None
    assert hass.states.get(climate.entity_id).state == HVACMode.COOL

    for platform, key in ALL_EXTRAS:
        entry = registry.async_get(_entity_id(hass, platform, f"{APN}_{key}"))
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entry.entity_id) is None

    # Good Sleep and Streamer are not exposed.
    for key in ("good_sleep", "streamer"):
        assert registry.async_get_entity_id("switch", DOMAIN, f"{APN}_{key}") is None


@pytest.mark.asyncio
async def test_enabled_switch_works_alone(hass: HomeAssistant, device) -> None:
    """An entity enabled on its own controls the device and follows the climate."""
    await _setup(hass, enable=(("switch", "econo"),))
    econo = _entity_id(hass, "switch", f"{APN}_econo")
    climate = _entity_id(hass, "climate", APN)
    # The other extras stay disabled.
    assert hass.states.get(_entity_id(hass, "switch", f"{APN}_powerchill")) is None

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: econo}, blocking=True
    )
    assert device.sent[-1] == {"econo": 1}
    assert hass.states.get(econo).state == "on"
    assert hass.states.get(climate).attributes[ATTR_PRESET_MODE] == PRESET_ECO

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: econo}, blocking=True
    )
    assert device.sent[-1] == {"econo": 0}
    assert hass.states.get(econo).state == "off"
    assert hass.states.get(climate).attributes[ATTR_PRESET_MODE] == PRESET_NONE


@pytest.mark.asyncio
async def test_climate_presets_sync_switches(hass: HomeAssistant, device) -> None:
    """Eco, Boost and None from the climate update the device and both switches."""
    await _setup(hass, enable=ALL_EXTRAS)
    climate = _entity_id(hass, "climate", APN)
    econo = _entity_id(hass, "switch", f"{APN}_econo")
    powerchill = _entity_id(hass, "switch", f"{APN}_powerchill")

    steps = [
        (PRESET_ECO, {"econo": 1}, "on", "off"),
        (PRESET_BOOST, {"powerchill": 1, "econo": 0}, "off", "on"),
        (PRESET_ECO, {"powerchill": 0, "econo": 1}, "on", "off"),
        (PRESET_NONE, {"econo": 0}, "off", "off"),
        (PRESET_BOOST, {"powerchill": 1}, "off", "on"),
        (PRESET_NONE, {"powerchill": 0}, "off", "off"),
    ]
    for preset, sent, econo_state, powerchill_state in steps:
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {ATTR_ENTITY_ID: climate, ATTR_PRESET_MODE: preset},
            blocking=True,
        )
        await hass.async_block_till_done()
        assert device.sent[-1] == sent, preset
        assert hass.states.get(climate).attributes[ATTR_PRESET_MODE] == preset
        assert hass.states.get(econo).state == econo_state, preset
        assert hass.states.get(powerchill).state == powerchill_state, preset


@pytest.mark.asyncio
async def test_switches_sync_climate_preset(hass: HomeAssistant, device) -> None:
    """Turning on Power Chill while Econo is on clears Econo everywhere."""
    await _setup(hass, enable=ALL_EXTRAS)
    climate = _entity_id(hass, "climate", APN)
    econo = _entity_id(hass, "switch", f"{APN}_econo")
    powerchill = _entity_id(hass, "switch", f"{APN}_powerchill")

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: econo}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: powerchill}, blocking=True
    )

    assert device.sent[-1] == {"powerchill": 1, "econo": 0}
    assert hass.states.get(econo).state == "off"
    assert hass.states.get(powerchill).state == "on"
    assert hass.states.get(climate).attributes[ATTR_PRESET_MODE] == PRESET_BOOST


@pytest.mark.asyncio
async def test_firmware_exclusion_reflected(hass: HomeAssistant, device) -> None:
    """When the firmware clears a preset on its own, every entity shows it."""
    await _setup(hass, enable=ALL_EXTRAS)
    climate = _entity_id(hass, "climate", APN)
    econo = _entity_id(hass, "switch", f"{APN}_econo")
    powerchill = _entity_id(hass, "switch", f"{APN}_powerchill")
    # Power Chill was turned on by the remote and HA has not polled yet.
    device.port["powerchill"] = 1

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: econo}, blocking=True
    )

    assert device.sent[-1] == {"econo": 1}
    assert hass.states.get(econo).state == "on"
    assert hass.states.get(powerchill).state == "off"
    assert hass.states.get(climate).attributes[ATTR_PRESET_MODE] == PRESET_ECO


@pytest.mark.asyncio
async def test_power_and_swing_sync(hass: HomeAssistant, device) -> None:
    """Power and vertical swing stay in step between the climate and switches."""
    await _setup(hass, enable=ALL_EXTRAS)
    climate = _entity_id(hass, "climate", APN)
    power = _entity_id(hass, "switch", f"{APN}_power")
    v_swing = _entity_id(hass, "switch", f"{APN}_v_swing")

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: power}, blocking=True
    )
    assert hass.states.get(climate).state == HVACMode.OFF
    await hass.services.async_call(
        "climate", "turn_on", {ATTR_ENTITY_ID: climate}, blocking=True
    )
    assert hass.states.get(power).state == "on"

    await hass.services.async_call(
        "climate",
        "set_swing_mode",
        {ATTR_ENTITY_ID: climate, ATTR_SWING_MODE: "vertical"},
        blocking=True,
    )
    assert hass.states.get(v_swing).state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: v_swing}, blocking=True
    )
    assert hass.states.get(climate).attributes[ATTR_SWING_MODE] == "off"


@pytest.mark.asyncio
async def test_fan_speed_sync(hass: HomeAssistant, device) -> None:
    """The select and the climate fan mode share all seven options."""
    await _setup(hass, enable=ALL_EXTRAS)
    climate = _entity_id(hass, "climate", APN)
    fan_speed = _entity_id(hass, "select", f"{APN}_fan_speed")

    assert hass.states.get(fan_speed).attributes["options"] == FAN_MODES
    assert hass.states.get(climate).attributes[ATTR_FAN_MODES] == FAN_MODES

    for option in FAN_MODES:
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: fan_speed, "option": option},
            blocking=True,
        )
        assert hass.states.get(climate).attributes[ATTR_FAN_MODE] == option

    for option in reversed(FAN_MODES):
        await hass.services.async_call(
            "climate",
            "set_fan_mode",
            {ATTR_ENTITY_ID: climate, ATTR_FAN_MODE: option},
            blocking=True,
        )
        assert hass.states.get(fan_speed).state == option


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [0, 7])
async def test_auto_mode_values(hass: HomeAssistant, device, mode) -> None:
    """Device mode values 0 and 7 still show as Auto."""
    device.port["mode"] = mode
    await _setup(hass)

    assert hass.states.get(_entity_id(hass, "climate", APN)).state == HVACMode.AUTO


@pytest.mark.asyncio
@pytest.mark.parametrize("capabilities", [TimeoutError("no answer"), None, "invalid"])
async def test_capabilities_unavailable(
    hass: HomeAssistant, device, capabilities
) -> None:
    """Without /device data the integration loads with every feature."""
    device.capabilities = capabilities
    entry = await _setup(hass, enable=ALL_EXTRAS)

    assert entry.runtime_data.capabilities == {}
    state = hass.states.get(_entity_id(hass, "climate", APN))
    assert HVACMode.HEAT in state.attributes[ATTR_HVAC_MODES]
    assert state.attributes[ATTR_SUPPORTED_FEATURES] & ClimateEntityFeature.SWING_MODE
    assert hass.states.get(_entity_id(hass, "switch", f"{APN}_v_swing")) is not None


@pytest.mark.asyncio
async def test_capabilities_cooling_only_no_swing(hass: HomeAssistant, device) -> None:
    """heat=0 hides Heat; v_sw=0 removes swing from the climate and the switch."""
    device.capabilities = {"heat": 0, "v_sw": 0}
    await _setup(hass)

    state = hass.states.get(_entity_id(hass, "climate", APN))
    assert HVACMode.HEAT not in state.attributes[ATTR_HVAC_MODES]
    assert not (
        state.attributes[ATTR_SUPPORTED_FEATURES] & ClimateEntityFeature.SWING_MODE
    )
    assert (
        er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{APN}_v_swing")
        is None
    )


@pytest.mark.asyncio
async def test_no_vertical_swing_keeps_coanda(hass: HomeAssistant, device) -> None:
    """v_sw=0 removes only the vertical option when the unit supports Coanda."""
    device.capabilities = {"v_sw": 0}
    device.port["coanda"] = 0
    await _setup(hass)

    state = hass.states.get(_entity_id(hass, "climate", APN))
    assert state.attributes[ATTR_SUPPORTED_FEATURES] & ClimateEntityFeature.SWING_MODE
    assert state.attributes["swing_modes"] == ["off", "coanda"]
