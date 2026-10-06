"""Hour-counter sensors for Sony Projector ADCP.

The projector's `timer ?` command answers a JSON array of counters, e.g.
    [{"operation":128},{"light_src":123},{"prev_light_src":0}]

On a lamp-based model (VPL-VW715ES) `light_src` is lamp hours, which is the
number that decides when a lamp needs replacing -- worth surfacing as a proper
sensor rather than burying in a media_player attribute.

The coordinator reads the counters every 15 minutes; they move by one unit per
hour of use.

A failed read keeps the last value instead of going unavailable. The counters
only advance while the lamp is lit, and the projector spends most of the day in
standby or unreachable, when the last reading is still exactly right. Going
unavailable there blanked the dashboard and gapped the history most of the day.
The last value is also restored across restarts (RestoreSensor), so it is
correct even if HA starts while the projector cannot be read.
"""
from typing import Optional

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SonyProjectorConfigEntry, SonyProjectorCoordinator
from .entity import SonyProjectorEntity

PARALLEL_UPDATES = 0

# ADCP timer key -> (translation key / unique_id suffix, enabled by default).
# The unique_id suffixes predate the coordinator and must not change.
COUNTERS = {
    "light_src": ("lamp_hours", True),
    "operation": ("operation_hours", True),
    "prev_light_src": ("prev_lamp_hours", False),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the projector hour counters."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        SonyProjectorHoursSensor(coordinator, key) for key in COUNTERS
    )


class SonyProjectorHoursSensor(SonyProjectorEntity, RestoreSensor):
    """An hour counter read from the projector's `timer` response."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: SonyProjectorCoordinator, counter_key: str) -> None:
        """Initialize the sensor."""
        uid_suffix, enabled = COUNTERS[counter_key]
        super().__init__(coordinator, uid_suffix)
        self._counter_key = counter_key
        self._attr_translation_key = uid_suffix
        self._attr_entity_registry_enabled_default = enabled
        self._attr_native_value: Optional[int] = None
        self._read_counter()

    def _read_counter(self) -> None:
        """Take the counter from the snapshot, keeping the last value if absent."""
        data = self.coordinator.data
        if data and data.timer and data.timer.get(self._counter_key) is not None:
            self._attr_native_value = data.timer[self._counter_key]

    async def async_added_to_hass(self) -> None:
        """Restore the last reading if the first poll could not get one."""
        await super().async_added_to_hass()
        if self._attr_native_value is not None:
            return
        if (last := await self.async_get_last_sensor_data()) is None:
            return
        if isinstance(last.native_value, (int, float)):
            self._attr_native_value = int(last.native_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._read_counter()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Unavailable only until there has ever been a reading; see module doc."""
        return self._attr_native_value is not None
