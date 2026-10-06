"""Config flow for Sony Projector ADCP integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.util.network import is_ip_address
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_USE_AUTH,
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USE_AUTH,
    DOMAIN,
)
from .protocol import CannotConnect, InvalidAuth, SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def validate_input(data: Dict[str, Any]) -> Optional[str]:
    """Open a session with the given settings; raise on failure.

    Returns the projector's serial number (None if it does not answer
    `serialnum ?`), which is the config entry's unique id.
    """
    projector = SonyProjectorADCP(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        password=data.get(CONF_PASSWORD, ""),
        use_auth=data.get(CONF_USE_AUTH, DEFAULT_USE_AUTH),
    )
    await projector.validate()
    try:
        return await projector.get_string_value("serialnum")
    finally:
        await projector.close()


async def _errors_for(data: Dict[str, Any]) -> tuple[Dict[str, str], Optional[str]]:
    """Validate ``data``; return form errors and the serial number."""
    try:
        serial = await validate_input(data)
    except InvalidAuth:
        return {"base": "invalid_auth"}, None
    except CannotConnect:
        return {"base": "cannot_connect"}, None
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}, None
    return {}, serial


def _connection_schema(defaults: Dict[str, Any]) -> Dict[Any, Any]:
    """Host/port/auth fields shared by the user and reconfigure steps."""
    return {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
        vol.Optional(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): cv.port,
        # Blank keeps the stored password.
        **_auth_schema(defaults, password_default=vol.UNDEFINED),
    }


def _auth_schema(
    defaults: Dict[str, Any], password_default: Any = DEFAULT_PASSWORD
) -> Dict[Any, Any]:
    """Authentication fields shared by every step.

    Only the factory default is ever pre-filled: a stored password would be
    sent to the frontend in the form schema.
    """
    return {
        vol.Optional(
            CONF_USE_AUTH, default=defaults.get(CONF_USE_AUTH, DEFAULT_USE_AUTH)
        ): bool,
        vol.Optional(CONF_PASSWORD, default=password_default): PASSWORD_SELECTOR,
    }


class SonyProjectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sony Projector ADCP.

    There is deliberately no options flow: the only settings are connection
    settings, which belong in entry.data and change through reconfigure (host,
    port, auth) or reauth (started automatically when the password is rejected).
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            errors, serial = await _errors_for(user_input)
            if not errors:
                # Keyed by serial: the same projector at a new address updates
                # the existing entry instead of becoming a duplicate.
                await self.async_set_unique_id(serial or user_input[CONF_HOST])
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    }
                )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME), data=user_input
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                **_auth_schema({}),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> FlowResult:
        """Follow a configured projector to a new IP address.

        The manifest's `registered_devices` matcher only fires for MACs already
        on one of this integration's devices, so this never offers to set up
        an unknown device -- it only updates the host of an existing entry.
        """
        device_registry = dr.async_get(self.hass)
        connection = (
            dr.CONNECTION_NETWORK_MAC,
            dr.format_mac(discovery_info.macaddress),
        )
        entry = next(
            (
                entry
                for entry in self._async_current_entries(include_ignore=False)
                if device_registry.async_get_device_by_connection(
                    connection, entry.entry_id
                )
            ),
            None,
        )
        if entry is None or entry.unique_id is None:
            return self.async_abort(reason="unknown_device")
        if not is_ip_address(entry.data[CONF_HOST]):
            # Configured by hostname: DNS already follows the projector, and
            # replacing the name with a raw IP would undo that choice.
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(entry.unique_id)
        # Updates the stored host and reloads the entry when it changed.
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        return self.async_abort(reason="already_configured")

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> FlowResult:
        """Start reauth after the projector rejected the stored password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Ask for the new password and verify it before saving."""
        entry = self._get_reauth_entry()
        errors: Dict[str, str] = {}

        if user_input is not None:
            errors, _serial = await _errors_for({**entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            # The stored password was just rejected; don't pre-fill it.
            data_schema=vol.Schema(
                _auth_schema(dict(entry.data), password_default=vol.UNDEFINED)
            ),
            errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Change host, port or authentication without re-adding the entry."""
        entry = self._get_reconfigure_entry()
        errors: Dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_PASSWORD):
                user_input.pop(CONF_PASSWORD, None)
            if user_input[CONF_HOST] != entry.data[CONF_HOST]:
                self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})

            errors, serial = await _errors_for({**entry.data, **user_input})
            if not errors:
                # Entries from before 1.3.0 are keyed by host until their
                # first setup re-keys them to the serial number.
                keyed_by_host = entry.unique_id == entry.data[CONF_HOST]
                if serial and not keyed_by_host and serial != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                owner = (
                    self.hass.config_entries.async_entry_for_domain_unique_id(
                        DOMAIN, serial
                    )
                    if serial
                    else None
                )
                if owner is not None and owner.entry_id != entry.entry_id:
                    # That projector is already configured as another entry.
                    return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=serial
                    or (user_input[CONF_HOST] if keyed_by_host else entry.unique_id),
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _connection_schema({**entry.data, **(user_input or {})})
            ),
            errors=errors,
        )
