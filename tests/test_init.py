"""Config entry setup outcomes."""
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState

from .conftest import entry_for
from .fake_projector import FakeProjector


async def test_setup_and_unload(hass, projector):
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("media_player.sony_projector").state == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_unreachable_retries(hass):
    fake = FakeProjector()
    await fake.start()
    entry = entry_for(fake)
    await fake.stop()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_bad_password_starts_reauth(hass, projector):
    entry = entry_for(projector, password="wrong")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
