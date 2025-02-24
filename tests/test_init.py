"""Tests for initializing the Daikin Smart AC (daikin_br) integration."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_br import async_setup_entry, async_unload_entry
from custom_components.daikin_br.const import DOMAIN


@pytest.mark.asyncio
async def test_async_setup_entry(hass):
    """Test that async_setup_entry sets up the config entry correctly."""
    # Create a dummy config entry using MockConfigEntry.
    entry = MockConfigEntry(
        domain=DOMAIN, data={"key": "value"}, unique_id="test_entry"
    )
    entry.add_to_hass(hass)

    # Call the setup function.
    result = await async_setup_entry(hass, entry)
    assert result is True

    # Verify that the entry data is stored under DOMAIN in hass.data.
    assert entry.entry_id in hass.data.get(DOMAIN, {})
    assert hass.data[DOMAIN][entry.entry_id] == {"key": "value"}


@pytest.mark.asyncio
async def test_async_unload_entry(hass):
    """Test that async_unload_entry unloads the config entry correctly."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"key": "value"}, unique_id="test_entry"
    )
    entry.add_to_hass(hass)

    # Simulate that the entry is stored in hass.data.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data

    result = await async_unload_entry(hass, entry)
    assert result is True

    # Verify that the entry is removed from hass.data.
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
