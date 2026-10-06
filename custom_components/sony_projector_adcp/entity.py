"""Base entity shared by every platform."""
from __future__ import annotations

from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import SonyProjectorCoordinator


class SonyProjectorEntity(CoordinatorEntity[SonyProjectorCoordinator]):
    """An entity on the projector device, fed by the shared coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SonyProjectorCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Sony",
            model="VPL-VW715ES",
        )


class SonyProjectorSettingEntity(SonyProjectorEntity):
    """A picture setting: only meaningful, and only settable, while on."""

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.is_on
