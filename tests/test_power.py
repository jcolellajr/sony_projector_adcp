"""Power commands: the projector acknowledges before its own status moves.

Observed 2026-10-07 on the VW715ES: 10 ms after accepting `power "on"` it still
answered `standby`, and 245 ms after accepting `power "off"` it still answered
`on`. The fake projector models that by going on answering the old phase until
a test moves it.
"""
from datetime import timedelta
import logging

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.sony_projector_adcp import coordinator as coordinator_module

from .conftest import entry_for

ENTITY = "media_player.sony_projector"


async def _setup(hass, projector, power_status):
    projector.set_power(power_status)
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _power(hass, service):
    await hass.services.async_call(
        "media_player", service, {"entity_id": ENTITY}, blocking=True
    )
    await hass.async_block_till_done()


async def _end_settle_window(hass):
    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=coordinator_module.POWER_SETTLE + 1),
    )
    # The confirming read runs as a config-entry background task.
    await hass.async_block_till_done(wait_background_tasks=True)


def _shown(hass):
    state = hass.states.get(ENTITY)
    return state.state, state.attributes.get("power_status")


async def test_turn_on_survives_a_stale_read(hass, projector):
    entry = await _setup(hass, projector, "standby")
    await _power(hass, "turn_on")  # the projector still answers "standby"
    assert _shown(hass) == ("on", "startup")

    await entry.runtime_data.async_refresh()  # a regular poll inside the window
    assert _shown(hass) == ("on", "startup")

    projector.set_power("on")
    await _end_settle_window(hass)  # the confirming read reports the truth
    assert _shown(hass) == ("on", "on")


async def test_turn_off_survives_a_stale_read(hass, projector):
    entry = await _setup(hass, projector, "on")
    await _power(hass, "turn_off")  # the projector still answers "on"
    assert _shown(hass) == ("off", "cooling1")

    await entry.runtime_data.async_refresh()
    assert _shown(hass) == ("off", "cooling1")

    projector.set_power("cooling2")
    await _end_settle_window(hass)
    assert _shown(hass) == ("off", "cooling2")


async def test_dropped_command_shows_once_the_window_ends(hass, projector):
    """A command the projector never acts on must not be shown as done for good."""
    await _setup(hass, projector, "standby")
    await _power(hass, "turn_on")
    assert _shown(hass) == ("on", "startup")

    await _end_settle_window(hass)  # it never moved
    assert _shown(hass) == ("off", "standby")


async def test_caught_up_read_ends_the_window(hass, projector):
    """Once the projector reports the commanded side, later reads are taken as-is."""
    entry = await _setup(hass, projector, "standby")
    await _power(hass, "turn_on")
    projector.set_power("startup")
    await entry.runtime_data.async_refresh()

    projector.set_power("standby")  # e.g. switched off with the IR remote
    await entry.runtime_data.async_refresh()
    assert _shown(hass) == ("off", "standby")


async def test_turn_on_while_cooling_is_sent_but_not_shown(hass, projector, caplog):
    """2026-10-07: power on during cooling2 was accepted (ok) and dropped."""
    entry = await _setup(hass, projector, "cooling2")
    projector.received.clear()
    await _power(hass, "turn_on")

    assert 'power "on"' in projector.received  # success semantics unchanged
    assert _shown(hass) == ("off", "cooling2")
    assert any(
        r.levelno == logging.WARNING and "cooling" in r.getMessage()
        for r in caplog.records
    )
    await entry.runtime_data.async_refresh()  # no window was opened
    assert _shown(hass) == ("off", "cooling2")


async def test_unload_cancels_the_confirming_read(hass, projector):
    entry = await _setup(hass, projector, "standby")
    coordinator = entry.runtime_data
    await _power(hass, "turn_on")
    assert coordinator._settle_unsub is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._settle_unsub is None
    projector.received.clear()
    await _end_settle_window(hass)
    assert projector.received == []


async def test_turn_off_inside_an_open_on_window(hass, projector):
    """A second command replaces the first window, and its stale read is held."""
    entry = await _setup(hass, projector, "standby")
    await _power(hass, "turn_on")
    projector.set_power("startup")
    await _power(hass, "turn_off")  # the projector still answers "startup"
    assert _shown(hass) == ("off", "cooling1")

    await entry.runtime_data.async_refresh()
    assert _shown(hass) == ("off", "cooling1")

    projector.set_power("cooling1")
    await _end_settle_window(hass)
    assert _shown(hass) == ("off", "cooling1")


async def test_turn_on_when_the_status_read_fails(hass, projector):
    """A failed pre-read is not "cooling": power on is sent and shown as before."""
    await _setup(hass, projector, "standby")
    projector.responses["power_status ?"] = "err_inactive"
    projector.received.clear()
    await _power(hass, "turn_on")

    assert projector.received[:2] == ["power_status ?", 'power "on"']
    assert _shown(hass) == ("on", "startup")
