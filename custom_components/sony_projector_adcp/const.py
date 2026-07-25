"""Constants for Sony Projector ADCP integration."""

DOMAIN = "sony_projector_adcp"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_PASSWORD = "password"
CONF_USE_AUTH = "use_auth"

# Defaults
DEFAULT_PORT = 53595
DEFAULT_PASSWORD = "Projector"
DEFAULT_USE_AUTH = True
DEFAULT_NAME = "Sony Projector"

# Update intervals
SCAN_INTERVAL = 30  # seconds

# Model note: the upstream constants were written for the VPL-XW5000, a *laser*
# projector. This fork targets the VPL-VW715ES, which is lamp-based. The
# differences are not cosmetic -- verified by querying the unit directly:
#   light_output_val -> err_cmd   (laser-only; does not exist here)
#   lamp_control     -> "low"     (the lamp-era equivalent)
#   motionflow       -> supported (VW-series; the XW5000 has no Motionflow)
#   3d_format        -> supported (VW-series only)
# Anything added below was confirmed against the hardware, not a datasheet.

# Input sources for VPL-VW715ES
INPUT_SOURCES = {
    "hdmi1": "HDMI 1",
    "hdmi2": "HDMI 2",
}

# Picture modes for VPL-VW715ES
PICTURE_MODES = {
    "cinema_film1": "Cinema Film 1",
    "cinema_film2": "Cinema Film 2",
    "reference": "Reference",
    "tv": "TV",
    "photo": "Photo",
    "game": "Game",
    "brt_cinema": "Bright Cinema",
    "brt_tv": "Bright TV",
    "user1": "User 1",
    "user2": "User 2",
    "user3": "User 3",
}

# Power states
POWER_STATE_MAP = {
    "standby": "off",
    "startup": "on",
    "on": "on",
    "cooling1": "off",
    "cooling2": "off",
}

# Commands
CMD_POWER_ON = 'power "on"'
CMD_POWER_OFF = 'power "off"'
CMD_POWER_STATUS = "power_status ?"
CMD_INPUT = 'input "{}"'
CMD_INPUT_STATUS = "input ?"
CMD_BLANK_ON = 'blank "on"'
CMD_BLANK_OFF = 'blank "off"'
CMD_BLANK_STATUS = "blank ?"
CMD_PICTURE_MODE = 'picture_mode "{}"'
CMD_PICTURE_MODE_STATUS = "picture_mode ?"

# Adjustment commands (menu_num type)
CMD_BRIGHTNESS = "brightness {}"
CMD_BRIGHTNESS_STATUS = "brightness ?"
CMD_CONTRAST = "contrast {}"
CMD_CONTRAST_STATUS = "contrast ?"
CMD_SHARPNESS = "sharpness {}"
CMD_SHARPNESS_STATUS = "sharpness ?"
# NOTE: light_output_val is deliberately absent. It is the XW5000's laser-output
# command and answers err_cmd on the VW715ES; polling it produced a logged error
# on every 30s update. Use lamp_control instead.

# Lamp control (VW715ES is lamp-based, not laser)
CMD_LAMP_CONTROL = 'lamp_control "{}"'
CMD_LAMP_CONTROL_STATUS = "lamp_control ?"
LAMP_CONTROL_MODES = {
    "low": "Low",
    "high": "High",
}

# Read/write picture settings confirmed present on this unit
MOTIONFLOW_MODES = {
    "off": "Off",
    "smooth_high": "Smooth High",
    "smooth_low": "Smooth Low",
    "impulse": "Impulse",
    "combination": "Combination",
    "true_cinema": "True Cinema",
}

ASPECT_MODES = {
    "normal": "Normal",
    "v_stretch": "V Stretch",
    "zoom_1_85": "1.85:1 Zoom",
    "zoom_2_35": "2.35:1 Zoom",
    "stretch": "Stretch",
    "squeeze": "Squeeze",
}

COLOR_TEMP_MODES = {
    "d93": "D93",
    "d75": "D75",
    "d65": "D65",
    "d55": "D55",
    "custom1": "Custom 1",
    "custom2": "Custom 2",
    "custom3": "Custom 3",
    "custom4": "Custom 4",
    "custom5": "Custom 5",
}

# Read-only telemetry. `timer` answers a JSON array, e.g.
#   [{"operation":128},{"light_src":123},{"prev_light_src":0}]
CMD_TIMER_STATUS = "timer ?"
CMD_SERIAL_STATUS = "serialnum ?"
CMD_MAC_STATUS = "mac_address ?"

# Simple string-valued settings polled into attributes.
# Keyed by ADCP command -> attribute name.
STRING_ATTRIBUTES = {
    "aspect": "aspect",
    "color_temp": "color_temp",
    "color_space": "color_space",
    "gamma_correction": "gamma_correction",
    "contrast_enh": "contrast_enhancer",
    "nr": "noise_reduction",
    "motionflow": "motionflow",
    "3d_format": "format_3d",
}

# Numeric settings polled into attributes, beyond the ones with services.
NUMERIC_ATTRIBUTES = {
    "color": "color",
    "hue": "hue",
}

# Reality Creation commands
CMD_REALITY_CREATION = 'real_cre "{}"'
CMD_REALITY_CREATION_STATUS = "real_cre ?"

# Remote key commands
CMD_KEY = 'key "{}"'
KEY_MENU = "menu"
KEY_RESET = "reset"
KEY_UP = "up"
KEY_DOWN = "down"
KEY_LEFT = "left"
KEY_RIGHT = "right"
KEY_ENTER = "enter"

# Responses
RESPONSE_OK = "ok"
ERROR_PREFIX = "err_"