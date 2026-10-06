"""The Sony Projector ADCP integration."""
import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import CONF_USE_AUTH, DEFAULT_PASSWORD, DEFAULT_USE_AUTH, DOMAIN
from .coordinator import (
    SonyProjectorConfigEntry,
    SonyProjectorCoordinator,
    adcp_issue_id,
)
from .protocol import SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> bool:
    """Set up Sony Projector ADCP from a config entry."""
    projector = SonyProjectorADCP(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD),
        entry.data.get(CONF_USE_AUTH, DEFAULT_USE_AUTH),
    )
    coordinator = SonyProjectorCoordinator(hass, entry, projector)

    # The first poll doubles as the connection test. An unreachable projector
    # raises ConfigEntryNotReady (HA retries with backoff, so the entry
    # self-recovers); a rejected password raises ConfigEntryAuthFailed, which
    # starts a reauth flow.
    await coordinator.async_config_entry_first_refresh()

    # Entries created before 1.3.0 are keyed by host. The serial number
    # survives an IP change, so re-key once it is known.
    serial = coordinator.identity.serial
    if (
        serial
        and entry.unique_id != serial
        and hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, serial) is None
    ):
        _LOGGER.info("Re-keying %s from %s to serial %s", entry.title, entry.unique_id, serial)
        hass.config_entries.async_update_entry(entry, unique_id=serial)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
        await coordinator.projector.close()
        # The Repair is deliberately kept: a reload does not fix a stuck ADCP
        # daemon. The next successful poll withdraws it.
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> None:
    """Drop the Repair and failure count of a deleted entry."""
    ir.async_delete_issue(hass, DOMAIN, adcp_issue_id(entry.entry_id))
    hass.data.get(DOMAIN, {}).get("failed_polls", {}).pop(entry.entry_id, None)
