"""Media Player entity for Sony Projector ADCP."""
import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    ASPECT_MODES,
    COLOR_TEMP_MODES,
    DEFAULT_NAME,
    DOMAIN,
    INPUT_SOURCES,
    LAMP_CONTROL_MODES,
    MOTIONFLOW_MODES,
    NUMERIC_ATTRIBUTES,
    PICTURE_MODES,
    POWER_STATE_MAP,
    STRING_ATTRIBUTES,
)
from .protocol import SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

# Poll every 30 seconds (module-level so HA's entity platform honors it)
SCAN_INTERVAL = timedelta(seconds=30)

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

# Range of the step services (increase_/decrease_brightness etc.).
STEP_MIN = 0
STEP_MAX = 100


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Sony Projector media player."""
    projector = hass.data[DOMAIN][config_entry.entry_id]
    name = config_entry.data.get(CONF_NAME, DEFAULT_NAME)
    
    async_add_entities([SonyProjectorMediaPlayer(projector, name, config_entry.entry_id)])
    
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
    )


class SonyProjectorMediaPlayer(MediaPlayerEntity):
    """Representation of a Sony Projector as a Media Player."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self, projector: SonyProjectorADCP, name: str, entry_id: str
    ) -> None:
        """Initialize the media player."""
        self._projector = projector
        self._attr_unique_id = f"{entry_id}_media_player"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": name,
            "manufacturer": "Sony",
            "model": "VPL-VW715ES",
        }
        self._attr_state = MediaPlayerState.OFF
        self._current_source = None
        self._is_blank = False
        self._picture_mode = None
        self._brightness = None
        self._contrast = None
        self._sharpness = None
        self._reality_creation = None
        self._lamp_control = None
        # Populated on the first successful poll and then left alone.
        self._identity_loaded = False
        # Free-form settings discovered by querying the unit; see const.py.
        self._settings: dict[str, Any] = {}
        # One reauth prompt per outage, not one per poll.
        self._reauth_requested = False

    def _set_available(self, available: bool) -> None:
        """Record availability, logging only the transitions.

        The projector is routinely unreachable (powered at the wall, network
        sleep), so per-poll failures are logged at debug in protocol.py and
        only the change of state is logged here.
        """
        if available and not self._attr_available:
            _LOGGER.info("Projector at %s is available again", self._projector.host)
        elif not available and self._attr_available:
            _LOGGER.info(
                "Projector at %s is unavailable: %s",
                self._projector.host,
                self._projector.describe_last_error(),
            )
        self._attr_available = available

        if available:
            self._reauth_requested = False
        elif self._projector.auth_failed and not self._reauth_requested:
            # The password changed under us; ask for the new one instead of
            # silently staying unavailable until the next restart.
            self._reauth_requested = True
            self.platform.config_entry.async_start_reauth(self.hass)

    def _require(self, result: bool, action: str) -> None:
        """Raise a user-visible error when the projector did not accept a command."""
        if not result:
            raise HomeAssistantError(
                f"Projector could not {action}: "
                f"{self._projector.describe_last_error()}"
            )

    async def async_update(self) -> None:
        """Update the state of the projector."""
        try:
            # Get power status. send_command() returns None on any connection
            # failure (it never raises), so a falsy result means the projector
            # is unreachable -- report unavailable instead of keeping stale state.
            power_status = await self._projector.get_power_status()
            if power_status is None:
                self._set_available(False)
                return
            self._attr_state = (
                MediaPlayerState.ON
                if POWER_STATE_MAP.get(power_status) == "on"
                else MediaPlayerState.OFF
            )
            
            # Get additional info if powered on
            if self._attr_state == MediaPlayerState.ON:
                # Get input source
                try:
                    source = await self._projector.get_input()
                    if source:
                        self._current_source = source
                except Exception as e:
                    _LOGGER.debug("Error getting input source: %s", e)
                
                # Get blank status
                try:
                    blank_status = await self._projector.get_blank_status()
                    if blank_status is not None:
                        self._is_blank = blank_status
                except Exception as e:
                    _LOGGER.debug("Error getting blank status: %s", e)
                
                # Get picture mode - keep last value if query fails
                try:
                    picture_mode = await self._projector.get_picture_mode()
                    if picture_mode:
                        self._picture_mode = picture_mode
                except Exception as e:
                    _LOGGER.debug("Error getting picture mode: %s", e)
                
                # Get brightness - keep last value if query fails
                try:
                    brightness = await self._projector.get_numeric_value("brightness")
                    if brightness is not None:
                        self._brightness = brightness
                except Exception as e:
                    _LOGGER.debug("Error getting brightness: %s", e)
                
                # Get contrast - keep last value if query fails
                try:
                    contrast = await self._projector.get_numeric_value("contrast")
                    if contrast is not None:
                        self._contrast = contrast
                except Exception as e:
                    _LOGGER.debug("Error getting contrast: %s", e)
                
                # Get sharpness - keep last value if query fails
                try:
                    sharpness = await self._projector.get_numeric_value("sharpness")
                    if sharpness is not None:
                        self._sharpness = sharpness
                except Exception as e:
                    _LOGGER.debug("Error getting sharpness: %s", e)
                
                # Lamp control replaces the XW5000's light_output_val, which
                # answers err_cmd on this lamp-based model.
                try:
                    lamp_control = await self._projector.get_string_value("lamp_control")
                    if lamp_control:
                        self._lamp_control = lamp_control
                except Exception as e:
                    _LOGGER.debug("Error getting lamp control: %s", e)

                # Get reality creation - keep last value if query fails
                try:
                    reality_creation = await self._projector.get_reality_creation()
                    if reality_creation:
                        self._reality_creation = reality_creation
                except Exception as e:
                    _LOGGER.debug("Error getting reality creation: %s", e)

                # Remaining settings, table-driven. A query that comes back
                # None (unsupported, or err_inactive for a signal-dependent
                # setting like hdr) leaves the previous value untouched.
                for command, attr in STRING_ATTRIBUTES.items():
                    try:
                        value = await self._projector.get_string_value(command)
                        if value is not None:
                            self._settings[attr] = value
                    except Exception as e:
                        _LOGGER.debug("Error getting %s: %s", command, e)

                for command, attr in NUMERIC_ATTRIBUTES.items():
                    try:
                        value = await self._projector.get_numeric_value(command)
                        if value is not None:
                            self._settings[attr] = value
                    except Exception as e:
                        _LOGGER.debug("Error getting %s: %s", command, e)
            else:
                # If powered off, clear these values
                self._brightness = None
                self._contrast = None
                self._sharpness = None
                self._picture_mode = None
                self._reality_creation = None
                self._lamp_control = None
                self._settings.clear()

        except Exception as e:
            _LOGGER.error("Error updating projector state: %s", e)
            self._set_available(False)
            return

        self._set_available(True)

    async def async_turn_on(self) -> None:
        """Turn the projector on."""
        self._require(await self._projector.set_power(True), "turn on")

    async def async_turn_off(self) -> None:
        """Turn the projector off."""
        self._require(await self._projector.set_power(False), "turn off")

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
        self._require(
            await self._projector.set_input(source_key), f"switch to {source}"
        )
        self._current_source = source_key

    async def async_send_key(self, key: str) -> None:
        """Send a remote control key command."""
        self._require(await self._projector.send_key(key), f"send key {key}")

    async def async_set_picture_mode_service(self, mode: str) -> None:
        """Set picture mode via service call."""
        self._require(
            await self._projector.set_picture_mode(mode), f"set picture mode {mode}"
        )
        self._picture_mode = mode

    async def _set_numeric(self, parameter: str, value: int) -> None:
        """Set brightness/contrast/sharpness and cache it only on success."""
        self._require(
            await self._projector.set_numeric_value(parameter, value),
            f"set {parameter} to {value}",
        )
        setattr(self, f"_{parameter}", value)

    async def _step_numeric(self, parameter: str, delta: int) -> None:
        """Move a numeric setting by ``delta`` from its current device value.

        Read fresh rather than from the poll cache: the cache can be up to 30s
        stale (or empty right after a restart), and stepping from a stale or
        assumed value makes the picture jump.
        """
        current = await self._projector.get_numeric_value(parameter)
        if current is None:
            raise HomeAssistantError(
                f"Projector could not read current {parameter}: "
                f"{self._projector.describe_last_error()}"
            )
        await self._set_numeric(
            parameter, max(STEP_MIN, min(current + delta, STEP_MAX))
        )

    async def async_set_brightness(self, value: int) -> None:
        """Set brightness via service call."""
        await self._set_numeric("brightness", value)

    async def async_set_contrast(self, value: int) -> None:
        """Set contrast via service call."""
        await self._set_numeric("contrast", value)

    async def async_set_sharpness(self, value: int) -> None:
        """Set sharpness via service call."""
        await self._set_numeric("sharpness", value)

    async def async_set_lamp_control(self, mode: str) -> None:
        """Set lamp output (low/high)."""
        self._require(
            await self._projector.set_string_value("lamp_control", mode),
            f"set lamp control to {mode}",
        )
        self._lamp_control = mode

    async def _set_setting(self, parameter: str, mode: str, label: str) -> None:
        """Set a table-driven string setting and cache it only on success."""
        self._require(
            await self._projector.set_string_value(parameter, mode),
            f"set {label} to {mode}",
        )
        self._settings[parameter] = mode

    async def async_set_motionflow(self, mode: str) -> None:
        """Set Motionflow mode."""
        await self._set_setting("motionflow", mode, "Motionflow")

    async def async_set_aspect(self, mode: str) -> None:
        """Set aspect ratio."""
        await self._set_setting("aspect", mode, "aspect")

    async def async_set_color_temp(self, mode: str) -> None:
        """Set colour temperature preset."""
        await self._set_setting("color_temp", mode, "colour temperature")

    async def async_increase_brightness(self) -> None:
        """Increase brightness by 1."""
        await self._step_numeric("brightness", 1)

    async def async_decrease_brightness(self) -> None:
        """Decrease brightness by 1."""
        await self._step_numeric("brightness", -1)

    async def async_increase_contrast(self) -> None:
        """Increase contrast by 1."""
        await self._step_numeric("contrast", 1)

    async def async_decrease_contrast(self) -> None:
        """Decrease contrast by 1."""
        await self._step_numeric("contrast", -1)

    async def async_increase_sharpness(self) -> None:
        """Increase sharpness by 1."""
        await self._step_numeric("sharpness", 1)

    async def async_decrease_sharpness(self) -> None:
        """Decrease sharpness by 1."""
        await self._step_numeric("sharpness", -1)

    async def async_set_reality_creation(self, state: str) -> None:
        """Set Reality Creation on or off."""
        self._require(
            await self._projector.set_reality_creation(state),
            f"set Reality Creation {state}",
        )
        self._reality_creation = state

    async def async_toggle_reality_creation(self) -> None:
        """Toggle Reality Creation on/off."""
        current = self._reality_creation if self._reality_creation else "off"
        new_state = "off" if current == "on" else "on"
        await self.async_set_reality_creation(new_state)

    async def async_send_raw_command(self, command: str) -> None:
        """Send a raw ADCP command to the projector."""
        response = await self._projector.send_command(command)
        if response is None:
            raise HomeAssistantError(
                f"Raw command {command!r} failed: "
                f"{self._projector.describe_last_error()}"
            )
        _LOGGER.info("Raw command '%s' returned: %s", command, response)

    @property
    def source(self) -> Optional[str]:
        """Return the current input source."""
        if self._current_source:
            return INPUT_SOURCES.get(self._current_source)
        return None

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return list(INPUT_SOURCES.values())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "video_muted": self._is_blank,
        }
        
        if self._picture_mode:
            attrs["picture_mode"] = PICTURE_MODES.get(self._picture_mode, self._picture_mode)
        
        if self._brightness is not None:
            attrs["brightness"] = self._brightness
        
        if self._contrast is not None:
            attrs["contrast"] = self._contrast
        
        if self._sharpness is not None:
            attrs["sharpness"] = self._sharpness

        if self._reality_creation is not None:
            attrs["reality_creation"] = self._reality_creation

        if self._lamp_control is not None:
            attrs["lamp_control"] = self._lamp_control

        # Table-driven settings (aspect, colour temp, Motionflow, ...).
        attrs.update(self._settings)

        return attrs