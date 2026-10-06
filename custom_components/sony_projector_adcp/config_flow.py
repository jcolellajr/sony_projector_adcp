"""Config flow for Sony Projector ADCP integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
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


async def validate_input(data: Dict[str, Any]) -> None:
    """Open one session with the given settings; raise on failure."""
    projector = SonyProjectorADCP(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        password=data.get(CONF_PASSWORD, ""),
        use_auth=data.get(CONF_USE_AUTH, DEFAULT_USE_AUTH),
    )
    await projector.validate()


async def _errors_for(data: Dict[str, Any]) -> Dict[str, str]:
    """Validate ``data`` and map failures to form error keys."""
    try:
        await validate_input(data)
    except InvalidAuth:
        return {"base": "invalid_auth"}
    except CannotConnect:
        return {"base": "cannot_connect"}
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected exception")
        return {"base": "unknown"}
    return {}


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
            # Check if already configured
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            errors = await _errors_for(user_input)
            if not errors:
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
            errors = await _errors_for({**entry.data, **user_input})
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
            # unique_id is the host, so a new host must not collide with
            # another configured projector.
            if user_input[CONF_HOST] != entry.unique_id:
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

            errors = await _errors_for({**entry.data, **user_input})
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=user_input[CONF_HOST],
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _connection_schema({**entry.data, **(user_input or {})})
            ),
            errors=errors,
        )
