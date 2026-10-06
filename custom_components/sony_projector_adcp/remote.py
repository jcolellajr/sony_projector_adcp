"""Remote entity: menu navigation keys via the standard remote.send_command."""
import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SonyProjectorConfigEntry
from .entity import SonyProjectorEntity
from .media_player import KEY_COMMANDS

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SonyProjectorConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remote."""
    async_add_entities([SonyProjectorRemote(config_entry.runtime_data, "remote")])


class SonyProjectorRemote(SonyProjectorEntity, RemoteEntity):
    """Sends remote-control keys (menu, up, down, left, right, enter, ...)."""

    # Named after the device: remote.sony_projector.
    _attr_name = None

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        keys = list(command)
        if unknown := [key for key in keys if key not in KEY_COMMANDS]:
            raise ServiceValidationError(
                f"Unknown key(s) {', '.join(unknown)}; expected one of "
                f"{', '.join(KEY_COMMANDS)}"
            )
        repeats = kwargs.get(ATTR_NUM_REPEATS, 1)
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        for i in range(repeats):
            for j, key in enumerate(keys):
                if i or j:
                    await asyncio.sleep(delay)
                await self.coordinator.async_send_key(key)
