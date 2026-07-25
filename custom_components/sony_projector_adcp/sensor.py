"""Hour-counter sensors for Sony Projector ADCP.

The projector's `timer ?` command answers a JSON array of counters, e.g.
    [{"operation":128},{"light_src":123},{"prev_light_src":0}]

On a lamp-based model (VPL-VW715ES) `light_src` is lamp hours, which is the
number that decides when a lamp needs replacing -- worth surfacing as a proper
sensor rather than burying in a media_player attribute.

Polled far less often than the media player: these move by one unit per hour of
use, and ADCP accepts only one session at a time, so there is no reason to
contend with the media player's 30s poll for a value that changes hourly.
"""
import logging
from datetime import timedelta
from typing import Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_NAME, DOMAIN
from .protocol import SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)

# ADCP timer key -> (entity name suffix, unique_id suffix, enabled by default)
COUNTERS = {
    "light_src": ("Lamp Hours", "lamp_hours", True),
    "operation": ("Operation Hours", "operation_hours", True),
    "prev_light_src": ("Previous Lamp Hours", "prev_lamp_hours", False),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the projector hour counters."""
    projector = hass.data[DOMAIN][config_entry.entry_id]
    name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)

    # update_before_add: the 15-minute interval otherwise leaves these at
    # "unknown" for a quarter of an hour after every restart.
    async_add_entities(
        (
            SonyProjectorHoursSensor(projector, name, config_entry.entry_id, key)
            for key in COUNTERS
        ),
        update_before_add=True,
    )


class SonyProjectorHoursSensor(SensorEntity):
    """An hour counter read from the projector's `timer` response."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        projector: SonyProjectorADCP,
        name: str,
        entry_id: str,
        counter_key: str,
    ) -> None:
        """Initialize the sensor."""
        label, uid_suffix, enabled = COUNTERS[counter_key]
        self._projector = projector
        self._counter_key = counter_key
        self._attr_name = label
        self._attr_unique_id = f"{entry_id}_{uid_suffix}"
        self._attr_entity_registry_enabled_default = enabled
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": name,
            "manufacturer": "Sony",
            "model": "VPL-VW715ES",
        }
        self._attr_native_value: Optional[int] = None

    async def async_update(self) -> None:
        """Read the hour counters."""
        try:
            counters = await self._projector.get_timer()
        except Exception as e:  # noqa: BLE001 - never let a poll kill the entity
            _LOGGER.debug("Error reading projector timers: %s", e)
            self._attr_available = False
            return

        if not counters:
            # Standby answers nothing useful; keep the last known reading
            # rather than blanking a monotonic counter.
            self._attr_available = False
            return

        value = counters.get(self._counter_key)
        if value is None:
            self._attr_available = False
            return

        self._attr_native_value = value
        self._attr_available = True
