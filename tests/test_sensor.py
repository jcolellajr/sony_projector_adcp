"""Hour-counter sensors."""
from homeassistant.core import State
from homeassistant.helpers.entity_component import async_update_entity
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from .conftest import entry_for
from .fake_projector import FakeProjector

LAMP = "sensor.sony_projector_lamp_hours"


async def _setup(hass, fake):
    entry = entry_for(fake)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_reads_lamp_hours(hass, projector):
    await _setup(hass, projector)
    assert hass.states.get(LAMP).state == "123"


async def test_keeps_last_value_when_read_fails(hass, projector):
    await _setup(hass, projector)
    projector.responses["timer ?"] = "err_inactive"
    await async_update_entity(hass, LAMP)
    assert hass.states.get(LAMP).state == "123"


async def test_restores_after_restart_when_unreadable(hass, projector):
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(LAMP, "120"),
                {"native_value": 120, "native_unit_of_measurement": "h"},
            )
        ],
    )
    projector.responses["timer ?"] = "err_inactive"
    await _setup(hass, projector)
    assert hass.states.get(LAMP).state == "120"


async def test_fresh_value_beats_restored(hass, projector):
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(LAMP, "120"),
                {"native_value": 120, "native_unit_of_measurement": "h"},
            )
        ],
    )
    await _setup(hass, projector)
    assert hass.states.get(LAMP).state == "123"


async def test_unavailable_without_any_reading(hass):
    fake = FakeProjector()
    await fake.start()
    fake.responses["timer ?"] = "err_inactive"
    try:
        await _setup(hass, fake)
        assert hass.states.get(LAMP).state == "unavailable"
    finally:
        await fake.stop()
