"""Picture-setting selects: picture mode, lamp, Motionflow, aspect, colour temp.

Options are the ADCP values (e.g. `cinema_film1`), so automations use the same
values as the services; translations supply the display names.
"""
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ASPECT_MODES,
    COLOR_TEMP_MODES,
    LAMP_CONTROL_MODES,
    MOTIONFLOW_MODES,
    PICTURE_MODES,
)
from .coordinator import SonyProjectorConfigEntry, SonyProjectorCoordinator
from .entity import SonyProjectorSettingEntity

PARALLEL_UPDATES = 0

# ADCP parameter -> (options, label used in error messages)
SELECTS = {
    "picture_mode": (PICTURE_MODES, "picture mode"),
    "lamp_control": (LAMP_CONTROL_MODES, "lamp control"),
    "motionflow": (MOTIONFLOW_MODES, "Motionflow"),
    "aspect": (ASPECT_MODES, "aspect"),
    "color_temp": (COLOR_TEMP_MODES, "colour temperature"),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the setting selects."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        SonyProjectorSelect(coordinator, parameter) for parameter in SELECTS
    )


class SonyProjectorSelect(SonyProjectorSettingEntity, SelectEntity):
    """One string-valued picture setting."""

    def __init__(self, coordinator: SonyProjectorCoordinator, parameter: str) -> None:
        super().__init__(coordinator, parameter)
        options, self._label = SELECTS[parameter]
        self._parameter = parameter
        self._attr_translation_key = parameter
        self._attr_options = list(options)

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.values.get(self._parameter)
        # A value this table does not know would be rejected by HA's select
        # state machine; report it as unknown rather than crash the entity.
        return value if value in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_string(self._parameter, option, self._label)
