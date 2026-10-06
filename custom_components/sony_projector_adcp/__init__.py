"""The Sony Projector ADCP integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_USE_AUTH, DEFAULT_PASSWORD, DEFAULT_USE_AUTH, DOMAIN
from .protocol import CannotConnect, InvalidAuth, SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sony Projector ADCP from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    password = entry.data.get(CONF_PASSWORD, DEFAULT_PASSWORD)
    use_auth = entry.data.get(CONF_USE_AUTH, DEFAULT_USE_AUTH)

    projector = SonyProjectorADCP(host, port, password, use_auth)

    # Test connection. Raise (not return False) so HA retries with backoff
    # and the entry self-recovers when the projector answers again. A rejected
    # password is not transient: ConfigEntryAuthFailed starts a reauth flow.
    try:
        await projector.validate()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed(
            f"Projector at {host}:{port} rejected the ADCP password"
        ) from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to projector at {host}:{port}"
        ) from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = projector

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        projector = hass.data[DOMAIN].pop(entry.entry_id)
        await projector.disconnect()

    return unload_ok
