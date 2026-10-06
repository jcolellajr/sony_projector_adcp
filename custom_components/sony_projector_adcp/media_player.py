"""Media Player entity for Sony Projector ADCP."""
import logging
from typing import Any, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
import voluptuous as vol

from .const import (
    ASPECT_MODES,
    COLOR_TEMP_MODES,
    INPUT_SOURCES,
    LAMP_CONTROL_MODES,
    MOTIONFLOW_MODES,
    NUMERIC_ATTRIBUTES,
    PICTURE_MODES,
    STRING_ATTRIBUTES,
)
from .coordinator import SonyProjectorConfigEntry
from .entity import SonyProjectorEntity

_LOGGER = logging.getLogger(__name__)

# Commands are serialized by the protocol lock; no need to limit here.
PARALLEL_UPDATES = 0

# Service schemas
SERVICE_SEND_KEY = "send_key"
SERVICE_SET_PICTURE_MODE = "set_picture_mode"
SERVICE_SET_BRIGHTNESS = "set_brightness"
SERVICE_SET_CONTRAST = "set_contrast"
SERVICE_SET_SHARPNESS = "set_sharpness"
SERVICE_SEND_RAW_COMMAND = "send_raw_command"
SERVICE_SET_LAMP_CONTROL = "set_lamp_control"
SERVICE_SET_MOTIONFLOW = "set_motionflow"
SERVICE_SET_ASPECT = "set_aspect"
SERVICE_SET_COLOR_TEMP = "set_color_temp"

ATTR_KEY = "key"
ATTR_MODE = "mode"
ATTR_VALUE = "value"
ATTR_COMMAND = "command"

KEY_COMMANDS = ["menu", "up", "down", "left", "right", "enter", "reset", "blank"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Sony Projector media player."""
    async_add_entities([SonyProjectorMediaPlayer(config_entry.runtime_data)])
    
    # Register services
    platform = async_get_current_platform()
    
    platform.async_register_entity_service(
        SERVICE_SEND_KEY,
        {vol.Required(ATTR_KEY): vol.In(KEY_COMMANDS)},
        "async_send_key",
    )
    
    platform.async_register_entity_service(
        SERVICE_SET_PICTURE_MODE,
        {vol.Required(ATTR_MODE): vol.In(list(PICTURE_MODES.keys()))},
        "async_set_picture_mode_service",
    )
    
    platform.async_register_entity_service(
        SERVICE_SET_BRIGHTNESS,
        {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))},
        "async_set_brightness",
    )
    
    platform.async_register_entity_service(
        SERVICE_SET_CONTRAST,
        {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))},
        "async_set_contrast",
    )
    
    platform.async_register_entity_service(
        SERVICE_SET_SHARPNESS,
        {vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))},
        "async_set_sharpness",
    )
    
    platform.async_register_entity_service(
        SERVICE_SET_LAMP_CONTROL,
        {vol.Required(ATTR_MODE): vol.In(list(LAMP_CONTROL_MODES.keys()))},
        "async_set_lamp_control",
    )

    platform.async_register_entity_service(
        SERVICE_SET_MOTIONFLOW,
        {vol.Required(ATTR_MODE): vol.In(list(MOTIONFLOW_MODES.keys()))},
        "async_set_motionflow",
    )

    platform.async_register_entity_service(
        SERVICE_SET_ASPECT,
        {vol.Required(ATTR_MODE): vol.In(list(ASPECT_MODES.keys()))},
        "async_set_aspect",
    )

    platform.async_register_entity_service(
        SERVICE_SET_COLOR_TEMP,
        {vol.Required(ATTR_MODE): vol.In(list(COLOR_TEMP_MODES.keys()))},
        "async_set_color_temp",
    )

    platform.async_register_entity_service(
        "increase_brightness",
        {},
        "async_increase_brightness",
    )
    
    platform.async_register_entity_service(
        "decrease_brightness",
        {},
        "async_decrease_brightness",
    )
    
    platform.async_register_entity_service(
        "increase_contrast",
        {},
        "async_increase_contrast",
    )
    
    platform.async_register_entity_service(
        "decrease_contrast",
        {},
        "async_decrease_contrast",
    )
    
    platform.async_register_entity_service(
        "increase_sharpness",
        {},
        "async_increase_sharpness",
    )
    
    platform.async_register_entity_service(
        "decrease_sharpness",
        {},
        "async_decrease_sharpness",
    )
    
    platform.async_register_entity_service(
        "set_reality_creation",
        {vol.Required("state"): vol.In(["on", "off"])},
        "async_set_reality_creation",
    )
    
    platform.async_register_entity_service(
        "toggle_reality_creation",
        {},
        "async_toggle_reality_creation",
    )
    
    platform.async_register_entity_service(
        SERVICE_SEND_RAW_COMMAND,
        {vol.Required(ATTR_COMMAND): str},
        "async_send_raw_command",
        # The projector's answer comes back to the caller (Developer Tools
        # shows it) instead of only going to the log.
        supports_response=SupportsResponse.OPTIONAL,
    )


class SonyProjectorMediaPlayer(SonyProjectorEntity, MediaPlayerEntity):
    """The projector as a media player: power, input, and every setting as
    attributes. The per-setting entities (select/number/switch) are the
    dashboard-friendly controls; the services here stay for automations."""

    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator) -> None:
        """Initialize the media player."""
        super().__init__(coordinator, "media_player")

    @property
    def state(self) -> MediaPlayerState:
        """On while on or warming up; off in standby or cooling down."""
        data = self.coordinator.data
        return MediaPlayerState.ON if data and data.is_on else MediaPlayerState.OFF

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        await self.coordinator.async_set_power(False)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        source_key = None
        for key, name in INPUT_SOURCES.items():
            if name == source:
                source_key = key
                break

        if source_key is None:
            raise ServiceValidationError(
                f"Unknown source {source!r}; expected one of "
                f"{', '.join(INPUT_SOURCES.values())}"
            )
        await self.coordinator.async_set_source(source_key, source)

    async def async_send_key(self, key: str) -> None:
        """Send a remote control key command."""
        await self.coordinator.async_send_key(key)

    async def async_set_picture_mode_service(self, mode: str) -> None:
        """Set picture mode via service call."""
        await self.coordinator.async_set_string("picture_mode", mode, "picture mode")

    async def async_set_brightness(self, value: int) -> None:
        """Set brightness via service call."""
        await self.coordinator.async_set_numeric("brightness", value)

    async def async_set_contrast(self, value: int) -> None:
        """Set contrast via service call."""
        await self.coordinator.async_set_numeric("contrast", value)

    async def async_set_sharpness(self, value: int) -> None:
        """Set sharpness via service call."""
        await self.coordinator.async_set_numeric("sharpness", value)

    async def async_set_lamp_control(self, mode: str) -> None:
        """Set lamp output (low/high)."""
        await self.coordinator.async_set_string("lamp_control", mode, "lamp control")

    async def async_set_motionflow(self, mode: str) -> None:
        """Set Motionflow mode."""
        await self.coordinator.async_set_string("motionflow", mode, "Motionflow")

    async def async_set_aspect(self, mode: str) -> None:
        """Set aspect ratio."""
        await self.coordinator.async_set_string("aspect", mode, "aspect")

    async def async_set_color_temp(self, mode: str) -> None:
        """Set colour temperature preset."""
        await self.coordinator.async_set_string(
            "color_temp", mode, "colour temperature"
        )

    async def async_increase_brightness(self) -> None:
        """Increase brightness by 1."""
        await self.coordinator.async_step_numeric("brightness", 1)

    async def async_decrease_brightness(self) -> None:
        """Decrease brightness by 1."""
        await self.coordinator.async_step_numeric("brightness", -1)

    async def async_increase_contrast(self) -> None:
        """Increase contrast by 1."""
        await self.coordinator.async_step_numeric("contrast", 1)

    async def async_decrease_contrast(self) -> None:
        """Decrease contrast by 1."""
        await self.coordinator.async_step_numeric("contrast", -1)

    async def async_increase_sharpness(self) -> None:
        """Increase sharpness by 1."""
        await self.coordinator.async_step_numeric("sharpness", 1)

    async def async_decrease_sharpness(self) -> None:
        """Decrease sharpness by 1."""
        await self.coordinator.async_step_numeric("sharpness", -1)

    async def async_set_reality_creation(self, state: str) -> None:
        """Set Reality Creation on or off."""
        await self.coordinator.async_set_string("real_cre", state, "Reality Creation")

    async def async_toggle_reality_creation(self) -> None:
        """Toggle Reality Creation on/off."""
        data = self.coordinator.data
        current = (data.values.get("real_cre") if data else None) or "off"
        new_state = "off" if current == "on" else "on"
        await self.async_set_reality_creation(new_state)

    async def async_send_raw_command(self, command: str) -> dict[str, Any]:
        """Send a raw ADCP command to the projector."""
        return {"response": await self.coordinator.async_send_raw(command)}

    @property
    def source(self) -> Optional[str]:
        """Return the current input source."""
        data = self.coordinator.data
        if data and data.source:
            return INPUT_SOURCES.get(data.source)
        return None

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return list(INPUT_SOURCES.values())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes.

        Names and values match the pre-coordinator entity so existing
        templates and automations keep working.
        """
        data = self.coordinator.data
        if data is None:
            return {}
        attrs: dict[str, Any] = {
            "video_muted": bool(data.blank),
            # Raw phase, e.g. startup / cooling1 -- the state alone is on/off.
            "power_status": data.power_status,
        }
        values = data.values if data.is_on else {}

        if picture_mode := values.get("picture_mode"):
            attrs["picture_mode"] = PICTURE_MODES.get(picture_mode, picture_mode)
        for parameter in ("brightness", "contrast", "sharpness"):
            if values.get(parameter) is not None:
                attrs[parameter] = values[parameter]
        if values.get("real_cre") is not None:
            attrs["reality_creation"] = values["real_cre"]
        if values.get("lamp_control") is not None:
            attrs["lamp_control"] = values["lamp_control"]

        # Table-driven settings (aspect, colour temp, Motionflow, ...).
        for table in (STRING_ATTRIBUTES, NUMERIC_ATTRIBUTES):
            for parameter, attr in table.items():
                if values.get(parameter) is not None:
                    attrs[attr] = values[parameter]

        return attrs
