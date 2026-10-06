"""Brightness, contrast and sharpness as number entities."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    NUMERIC_MAX,
    NUMERIC_MIN,
    SonyProjectorConfigEntry,
    SonyProjectorCoordinator,
)
from .entity import SonyProjectorSettingEntity

PARALLEL_UPDATES = 0

NUMBERS = ("brightness", "contrast", "sharpness")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the numeric picture settings."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        SonyProjectorNumber(coordinator, parameter) for parameter in NUMBERS
    )


class SonyProjectorNumber(SonyProjectorSettingEntity, NumberEntity):
    """One numeric picture setting."""

    _attr_native_min_value = NUMERIC_MIN
    _attr_native_max_value = NUMERIC_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: SonyProjectorCoordinator, parameter: str) -> None:
        super().__init__(coordinator, parameter)
        self._parameter = parameter
        self._attr_translation_key = parameter

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.values.get(self._parameter)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_numeric(self._parameter, int(value))
