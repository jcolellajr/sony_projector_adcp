"""Config, reauth and reconfigure flows."""
import json
from pathlib import Path

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.sony_projector_adcp.const import CONF_USE_AUTH, DOMAIN

from .conftest import entry_for
from .fake_projector import FakeProjector

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def _user_flow(hass, data):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def test_user_flow_creates_entry(hass, projector):
    result = await _user_flow(
        hass,
        {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_PASSWORD: "Projector"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Sony Projector"
    assert result["data"][CONF_PASSWORD] == "Projector"


async def test_user_flow_invalid_auth(hass, projector):
    result = await _user_flow(
        hass,
        {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_PASSWORD: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass):
    fake = FakeProjector()
    await fake.start()
    port = fake.port
    await fake.stop()
    result = await _user_flow(hass, {CONF_HOST: "127.0.0.1", CONF_PORT: port})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_updates_password(hass, projector):
    entry = entry_for(projector, password="old")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USE_AUTH: True, CONF_PASSWORD: "still wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USE_AUTH: True, CONF_PASSWORD: "Projector"}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "Projector"


async def test_reconfigure_changes_port(hass, projector):
    other = FakeProjector()
    await other.start()
    try:
        entry = entry_for(other)
        entry.add_to_hass(hass)
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "127.0.0.1",
                CONF_PORT: projector.port,
                CONF_USE_AUTH: True,
                CONF_PASSWORD: "Projector",
            },
        )
        assert result["type"] is FlowResultType.ABORT
        await hass.async_block_till_done()
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_PORT] == projector.port
    finally:
        await other.stop()


def _default(result, key):
    """The default a form pre-fills for ``key`` (None if none)."""
    for marker in result["data_schema"].schema:
        if marker == key:
            default = marker.default
            return None if default is vol.UNDEFINED else default()
    raise KeyError(key)


async def test_reauth_does_not_prefill_password(hass, projector):
    entry = entry_for(projector, password="secret-but-rejected")
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert _default(result, CONF_PASSWORD) is None


async def test_reconfigure_blank_password_keeps_current(hass, projector):
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert _default(result, CONF_PASSWORD) is None

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_USE_AUTH: True},
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "Projector"


async def test_no_options_flow(hass, projector):
    """The broken options flow was removed; reconfigure replaces it."""
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    assert not entry.supports_options


def test_translations_match_strings():
    """HA reads translations/en.json for custom integrations; keep it in sync."""
    strings = json.loads((COMPONENT / "strings.json").read_text())
    english = json.loads((COMPONENT / "translations" / "en.json").read_text())
    assert strings == english
