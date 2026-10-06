"""Video mute and Reality Creation as switches."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SonyProjectorConfigEntry
from .entity import SonyProjectorSettingEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            SonyProjectorVideoMute(coordinator, "video_mute"),
            SonyProjectorRealityCreation(coordinator, "reality_creation"),
        ]
    )


class SonyProjectorVideoMute(SonyProjectorSettingEntity, SwitchEntity):
    """Picture mute (ADCP `blank`). The key-based toggle can drift; this sets
    the state explicitly."""

    _attr_translation_key = "video_mute"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.blank

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_blank(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_blank(False)


class SonyProjectorRealityCreation(SonyProjectorSettingEntity, SwitchEntity):
    """Reality Creation (ADCP `real_cre`)."""

    _attr_translation_key = "reality_creation"

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.values.get("real_cre")
        return None if value is None else value == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_string("real_cre", "on", "Reality Creation")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_string("real_cre", "off", "Reality Creation")
