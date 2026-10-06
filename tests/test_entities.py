"""Select, number, switch and remote entities."""
import json
from pathlib import Path

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.sony_projector_adcp.const import DOMAIN
from custom_components.sony_projector_adcp.select import SELECTS

from .conftest import entry_for

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN


@pytest.fixture
async def loaded(hass, projector):
    projector.set_power("on")
    projector.responses.update(
        {
            "input ?": '"hdmi1"',
            "blank ?": '"off"',
            "picture_mode ?": '"reference"',
            "lamp_control ?": '"low"',
            "real_cre ?": '"on"',
            "aspect ?": '"normal"',
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


async def _call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, **data}, blocking=True
    )


async def test_one_poll_feeds_every_entity(hass, projector, loaded):
    projector.received.clear()
    await loaded.runtime_data.async_refresh()
    assert projector.received.count("power_status ?") == 1
    assert projector.received.count("brightness ?") == 1
    assert hass.states.get("select.sony_projector_picture_mode").state == "reference"
    assert hass.states.get("number.sony_projector_brightness").state == "50"
    assert hass.states.get("switch.sony_projector_reality_creation").state == "on"
    assert hass.states.get("switch.sony_projector_video_mute").state == "off"
    # Not answered by the fake projector -> unknown, not an error.
    assert hass.states.get("select.sony_projector_motionflow").state == "unknown"


async def test_select_option(hass, projector, loaded):
    projector.received.clear()
    await _call(
        hass, "select", "select_option", "select.sony_projector_aspect_ratio",
        option="zoom_2_35",
    )
    assert projector.received == ['aspect "zoom_2_35"']
    assert hass.states.get("select.sony_projector_aspect_ratio").state == "zoom_2_35"


async def test_picture_mode_change_repolls(hass, projector, loaded):
    """Brightness etc. are per picture mode, so a mode change re-reads them."""
    projector.responses["brightness ?"] = "58"
    await _call(
        hass, "select", "select_option", "select.sony_projector_picture_mode",
        option="cinema_film1",
    )
    await hass.async_block_till_done()
    assert hass.states.get("number.sony_projector_brightness").state == "58"


async def test_rejected_select_keeps_state(hass, projector, loaded):
    projector.responses['lamp_control "high"'] = "err_inactive"
    with pytest.raises(HomeAssistantError, match="lamp control"):
        await _call(
            hass, "select", "select_option", "select.sony_projector_lamp_control",
            option="high",
        )
    assert hass.states.get("select.sony_projector_lamp_control").state == "low"


async def test_number_set(hass, projector, loaded):
    projector.received.clear()
    await _call(
        hass, "number", "set_value", "number.sony_projector_contrast", value=45
    )
    assert projector.received == ["contrast 45"]
    assert hass.states.get("number.sony_projector_contrast").state == "45"


async def test_switches(hass, projector, loaded):
    projector.received.clear()
    await _call(hass, "switch", "turn_on", "switch.sony_projector_video_mute")
    await _call(hass, "switch", "turn_off", "switch.sony_projector_reality_creation")
    assert projector.received == ['blank "on"', 'real_cre "off"']
    assert hass.states.get("switch.sony_projector_video_mute").state == "on"
    assert hass.states.get("switch.sony_projector_reality_creation").state == "off"


async def test_settings_unavailable_while_off(hass, projector, loaded):
    projector.set_power("standby")
    await loaded.runtime_data.async_refresh()
    for entity_id in (
        "select.sony_projector_picture_mode",
        "number.sony_projector_brightness",
        "switch.sony_projector_video_mute",
    ):
        assert hass.states.get(entity_id).state == "unavailable", entity_id
    assert hass.states.get("media_player.sony_projector").state == "off"
    assert hass.states.get("remote.sony_projector").state == "off"


async def test_remote_send_command(hass, projector, loaded):
    projector.received.clear()
    await _call(
        hass, "remote", "send_command", "remote.sony_projector",
        command=["menu", "down"], num_repeats=2, delay_secs=0,
    )
    assert projector.received == [
        'key "menu"', 'key "down"', 'key "menu"', 'key "down"'
    ]


async def test_remote_rejects_unknown_key(hass, projector, loaded):
    projector.received.clear()
    with pytest.raises(ServiceValidationError, match="volume_up"):
        await _call(
            hass, "remote", "send_command", "remote.sony_projector",
            command=["menu", "volume_up"],
        )
    assert projector.received == []


def test_every_select_option_has_a_label():
    strings = json.loads((COMPONENT / "strings.json").read_text())
    for parameter, (options, _label) in SELECTS.items():
        labels = strings["entity"]["select"][parameter]["state"]
        assert set(labels) == set(options), parameter


async def test_blank_key_updates_video_mute(hass, projector, loaded):
    projector.responses["blank ?"] = '"on"'
    await _call(
        hass, "remote", "send_command", "remote.sony_projector", command=["blank"]
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.sony_projector_video_mute").state == "on"


async def test_command_during_poll_is_not_reverted(hass, projector, loaded):
    """A poll that read brightness before a command must not put it back."""
    import asyncio

    coordinator = loaded.runtime_data
    release = asyncio.Event()
    projector.hold["sharpness ?"] = release  # brightness ? is already read
    poll = hass.async_create_task(coordinator.async_refresh())
    await projector.holding.wait()

    command = hass.async_create_task(
        _call(hass, "number", "set_value", "number.sony_projector_brightness", value=70)
    )
    await asyncio.sleep(0)
    release.set()
    await command
    await poll
    assert hass.states.get("number.sony_projector_brightness").state == "70"


async def test_no_session_after_unload(hass, projector, loaded):
    coordinator = loaded.runtime_data
    assert await hass.config_entries.async_unload(loaded.entry_id)
    projector.received.clear()
    assert await coordinator.projector.get_power_status() is None
    assert coordinator.projector.describe_last_error() == "connection closed"
    assert projector.received == []
