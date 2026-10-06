"""Media player service behaviour."""
import logging

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.sony_projector_adcp.const import DOMAIN

from .conftest import entry_for

ENTITY = "media_player.sony_projector"


@pytest.fixture
async def loaded(hass, projector):
    projector.set_power("on")
    projector.responses.update(
        {
            "input ?": '"hdmi1"',
            "brightness ?": "50",
            "contrast ?": "40",
            "sharpness ?": "10",
        }
    )
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _call(hass, service, domain=DOMAIN, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": ENTITY, **data}, blocking=True
    )


async def test_rejected_command_raises(hass, projector, loaded):
    projector.responses['power "off"'] = "err_inactive"
    with pytest.raises(HomeAssistantError, match="could not turn off.*err_inactive"):
        await _call(hass, "turn_off", domain="media_player")


async def test_rejected_setting_is_not_cached(hass, projector, loaded):
    projector.responses["brightness 70"] = "err_val"
    projector.responses["brightness ?"] = "50"
    with pytest.raises(HomeAssistantError, match="value out of range"):
        await _call(hass, "set_brightness", value=70)
    assert hass.states.get(ENTITY).attributes["brightness"] == 50


async def test_step_reads_current_value(hass, projector, loaded):
    """+1 steps from what the projector reports now, not a cached or assumed 50."""
    projector.responses["brightness ?"] = "62"
    projector.received.clear()
    await _call(hass, "increase_brightness")
    assert "brightness 63" in projector.received


async def test_step_clamps(hass, projector, loaded):
    projector.responses["sharpness ?"] = "0"
    projector.received.clear()
    await _call(hass, "decrease_sharpness")
    assert "sharpness 0" in projector.received


async def test_step_without_reading_raises(hass, projector, loaded):
    projector.responses["contrast ?"] = "err_inactive"
    with pytest.raises(HomeAssistantError, match="could not read current contrast"):
        await _call(hass, "increase_contrast")


async def test_unknown_source_is_validation_error(hass, loaded):
    with pytest.raises(ServiceValidationError):
        await _call(hass, "select_source", domain="media_player", source="HDMI 9")


async def test_select_source(hass, projector, loaded):
    projector.received.clear()
    await _call(hass, "select_source", domain="media_player", source="HDMI 2")
    assert 'input "hdmi2"' in projector.received


async def test_raw_command_failure_raises(hass, projector, loaded):
    with pytest.raises(HomeAssistantError, match="err_cmd"):
        await _call(hass, "send_raw_command", command="bogus ?")


async def test_unavailable_then_recovers(hass, projector, loaded, caplog):
    coordinator = loaded.runtime_data
    projector.password = "changed-on-device"
    projector.drop_sessions()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "unavailable"
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]

    # Further failed polls neither log again nor stack up reauth prompts.
    caplog.clear()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert "Authentication failed" not in caplog.text
    assert len(hass.config_entries.flow.async_progress()) == 1

    projector.password = "Projector"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "on"
    assert "recovered" in caplog.text


async def test_unreachable_logs_once(hass, projector, loaded, caplog):
    coordinator = loaded.runtime_data
    coordinator.projector.port = 1  # nothing listens there
    projector.drop_sessions()
    caplog.clear()
    for _ in range(3):
        await coordinator.async_refresh()
    assert hass.states.get(ENTITY).state == "unavailable"
    loud = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "unreachable" in r.getMessage()
    ]
    assert len(loud) == 1


async def test_service_call_does_not_repoll(hass, projector, loaded):
    """A setting change sends one command, not a full ~19-command poll."""
    projector.received.clear()
    await _call(hass, "set_brightness", value=70)
    await hass.async_block_till_done()
    assert projector.received == ["brightness 70"]
    assert hass.states.get(ENTITY).attributes["brightness"] == 70


async def test_raw_command_returns_response(hass, projector, loaded):
    projector.responses["lamp_control ?"] = '"low"'
    result = await hass.services.async_call(
        DOMAIN,
        "send_raw_command",
        {"entity_id": ENTITY, "command": "lamp_control ?"},
        blocking=True,
        return_response=True,
    )
    assert result == {ENTITY: {"response": '"low"'}}


async def test_turn_on_shows_warmup_immediately(hass, projector):
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "off"

    projector.responses["power_status ?"] = '"startup"'
    await _call(hass, "turn_on", domain="media_player")
    state = hass.states.get(ENTITY)
    assert state.state == "on"
    assert state.attributes["power_status"] == "startup"
    await hass.async_block_till_done()


async def test_unique_id_unchanged(hass, loaded):
    """Entity registry entries from before the coordinator must keep matching."""
    registry = er.async_get(hass)
    assert registry.async_get(ENTITY).unique_id == f"{loaded.entry_id}_media_player"
