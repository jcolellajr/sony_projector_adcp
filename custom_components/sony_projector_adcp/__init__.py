"""The Sony Projector ADCP integration."""
import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_USE_AUTH, DEFAULT_PASSWORD, DEFAULT_USE_AUTH
from .coordinator import SonyProjectorConfigEntry, SonyProjectorCoordinator
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

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()
        await coordinator.projector.close()
    return unload_ok
