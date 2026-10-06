"""Serial-number identity, DHCP address following, and the ADCP Repair."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.sony_projector_adcp.const import CONF_USE_AUTH, DOMAIN
from custom_components.sony_projector_adcp.coordinator import WEDGE_POLLS, adcp_issue_id

from .conftest import entry_for
from .fake_projector import FakeProjector

MAC = "94:db:56:7b:0d:9d"
SERIAL = "5100123"


async def _setup(hass, entry):
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
        entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_legacy_entry_is_rekeyed_to_serial(hass, projector):
    entry = await _setup(hass, entry_for(projector))
    assert entry.unique_id == SERIAL


async def test_device_has_serial_mac_and_model(hass, projector):
    entry = await _setup(hass, entry_for(projector))
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device.serial_number == SERIAL
    assert device.model == "VPL-VW715ES"
    assert (dr.CONNECTION_NETWORK_MAC, MAC) in device.connections


async def test_user_flow_same_projector_new_address_updates_entry(hass, projector):
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, unique_id=SERIAL, data={**entry.data, CONF_HOST: "localhost"}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port, CONF_PASSWORD: "Projector"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"
    await hass.async_block_till_done()


async def test_reconfigure_to_other_projector_is_refused(hass, projector):
    other = FakeProjector()
    other.responses["serialnum ?"] = '"9999999"'
    await other.start()
    try:
        entry = await _setup(hass, entry_for(projector))
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: other.port, CONF_USE_AUTH: True},
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "wrong_device"
        assert entry.data[CONF_PORT] == projector.port
    finally:
        await other.stop()


async def test_dhcp_follows_projector_to_new_address(hass, projector):
    entry = await _setup(hass, entry_for(projector))
    # Pretend the stored address went stale while the entry stays loaded.
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HOST: "127.0.0.3"}
    )
    result = await _dhcp(hass, ip="127.0.0.1")
    await hass.async_block_till_done()
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"
    assert hass.states.get("media_player.sony_projector").state == "off"


async def test_dhcp_keeps_a_hostname(hass, projector):
    entry = entry_for(projector)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_HOST: "localhost"}
    )
    await _setup(hass, entry)
    result = await _dhcp(hass, ip="127.0.0.1")
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "localhost"


async def _dhcp(hass, ip, mac="94db567b0d9d"):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=DhcpServiceInfo(ip=ip, hostname="vpl-vw715es", macaddress=mac),
    )


async def test_dhcp_ignores_unknown_mac(hass, projector):
    await _setup(hass, entry_for(projector))
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=DhcpServiceInfo(ip="127.0.0.9", hostname="x", macaddress="001122334455"),
    )
    assert result["reason"] == "unknown_device"


async def _fail_polls(coordinator, n):
    for _ in range(n):
        await coordinator.async_refresh()


async def test_repair_when_adcp_fails_but_projector_is_up(hass, projector):
    entry = await _setup(hass, entry_for(projector))
    coordinator = entry.runtime_data
    issue_id = adcp_issue_id(entry.entry_id)
    sdcp = FakeProjector()  # stands in for the projector's other control port
    await sdcp.start()
    try:
        coordinator.projector.port = await _closed_port()
        projector.drop_sessions()
        with patch(
            "custom_components.sony_projector_adcp.coordinator.OTHER_PORTS",
            (sdcp.port,),
        ):
            await _fail_polls(coordinator, WEDGE_POLLS - 1)
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
            await _fail_polls(coordinator, 1)
            issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
            assert issue is not None
            assert issue.translation_key == "adcp_unresponsive"

        coordinator.projector.port = projector.port
        await coordinator.async_refresh()
        assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    finally:
        await sdcp.stop()


async def test_no_repair_when_projector_is_off_the_network(hass, projector):
    entry = await _setup(hass, entry_for(projector))
    coordinator = entry.runtime_data
    closed = await _closed_port()
    coordinator.projector.port = closed
    projector.drop_sessions()
    with patch(
        "custom_components.sony_projector_adcp.coordinator.OTHER_PORTS", (closed,)
    ):
        await _fail_polls(coordinator, WEDGE_POLLS + 2)
    assert ir.async_get(hass).async_get_issue(DOMAIN, adcp_issue_id(entry.entry_id)) is None


async def _closed_port() -> int:
    fake = FakeProjector()
    await fake.start()
    port = fake.port
    await fake.stop()
    return port


async def test_repair_raised_across_setup_retries(hass, projector):
    """ADCP stuck at startup: each retry is a new coordinator's first poll."""
    from homeassistant.config_entries import ConfigEntryState

    sdcp = FakeProjector()
    await sdcp.start()
    entry = entry_for(projector)
    adcp_port = projector.port
    await projector.stop()  # ADCP down, "SDCP" up
    try:
        with patch(
            "custom_components.sony_projector_adcp.coordinator.OTHER_PORTS",
            (sdcp.port,),
        ):
            entry.add_to_hass(hass)
            await hass.config_entries.async_setup(entry.entry_id)
            for _ in range(WEDGE_POLLS - 1):
                await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.SETUP_RETRY
            issue_id = adcp_issue_id(entry.entry_id)
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

            # A reload does not fix a stuck daemon, so it keeps the Repair.
            await hass.config_entries.async_reload(entry.entry_id)
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

        # ADCP answers again: the next successful setup withdraws it.
        revived = FakeProjector()
        await revived.start(port=adcp_port)
        try:
            await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.LOADED
            assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
        finally:
            await revived.stop()
    finally:
        await sdcp.stop()


async def test_repair_reraised_after_restart(hass, projector):
    """After a restart HA restores issues as inactive stubs; those must not
    suppress the Repair while ADCP is still stuck."""
    import dataclasses

    entry = await _setup(hass, entry_for(projector))
    coordinator = entry.runtime_data
    issue_id = adcp_issue_id(entry.entry_id)
    registry = ir.async_get(hass)
    sdcp = FakeProjector()
    await sdcp.start()
    try:
        coordinator.projector.port = await _closed_port()
        projector.drop_sessions()
        with patch(
            "custom_components.sony_projector_adcp.coordinator.OTHER_PORTS",
            (sdcp.port,),
        ):
            await _fail_polls(coordinator, WEDGE_POLLS)
            assert registry.async_get_issue(DOMAIN, issue_id).active

            # Simulate a restart: registry stub restored inactive, count reset.
            key = (DOMAIN, issue_id)
            registry.issues[key] = dataclasses.replace(registry.issues[key], active=False)
            hass.data[DOMAIN]["failed_polls"].clear()

            await _fail_polls(coordinator, WEDGE_POLLS)
            assert registry.async_get_issue(DOMAIN, issue_id).active
    finally:
        await sdcp.stop()
