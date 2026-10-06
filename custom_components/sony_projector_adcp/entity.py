"""Base entity shared by every platform."""
from __future__ import annotations

from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
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
        identity = coordinator.identity
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Sony",
            model=identity.model or "VPL-VW715ES",
            # The MAC links this device to the router's view of it and lets
            # DHCP discovery follow the projector to a new IP address.
            connections=(
                {(CONNECTION_NETWORK_MAC, identity.mac)} if identity.mac else set()
            ),
        )
        if identity.serial:
            # Only when known: an explicit None would erase a stored serial
            # after a setup whose identity read failed.
            self._attr_device_info["serial_number"] = identity.serial


class SonyProjectorSettingEntity(SonyProjectorEntity):
    """A picture setting: only meaningful, and only settable, while on."""

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.is_on
