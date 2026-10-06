"""One shared poll of the projector for every entity.

Before this, the media player polled ~19 commands every 30s on its own, the
hour sensors polled separately, and HA forced a full media-player poll after
every entity service call (so five taps of brightness+ cost ~95 round-trips).
Every entity now reads from one snapshot, and a successful command patches the
snapshot in place instead of re-polling.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
import logging
import time
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    NUMERIC_ATTRIBUTES,
    POWER_STATE_MAP,
    STRING_ATTRIBUTES,
)
from .protocol import SonyProjectorADCP

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)
# The hour counters move by one unit per hour of lamp use.
TIMER_INTERVAL = 15 * 60  # seconds

# Settings polled while the projector is on, by ADCP parameter name.
STRING_SETTINGS = ["picture_mode", "lamp_control", "real_cre", *STRING_ATTRIBUTES]
NUMERIC_SETTINGS = ["brightness", "contrast", "sharpness", *NUMERIC_ATTRIBUTES]

# Range of the numeric controls and step services.
NUMERIC_MIN = 0
NUMERIC_MAX = 100


@dataclass
class ProjectorState:
    """A snapshot of what the projector last reported."""

    power_status: str
    source: Optional[str] = None
    blank: Optional[bool] = None
    # Picture settings keyed by ADCP parameter name, e.g. "picture_mode".
    values: dict[str, Any] = field(default_factory=dict)
    # Hour counters from `timer ?`; kept across failed reads and power-off.
    timer: Optional[dict[str, int]] = None

    @property
    def is_on(self) -> bool:
        """Whether the projector is on (warming up counts as on)."""
        return POWER_STATE_MAP.get(self.power_status) == "on"


def _with_changes(state: ProjectorState, changes: dict[str, Any]) -> ProjectorState:
    """A copy of ``state`` with ``changes`` applied; ``values`` is merged."""
    if not changes:
        return state
    changes = dict(changes)
    values = changes.pop("values", None)
    new = replace(state, **changes)
    if values:
        new.values = {**state.values, **values}
    return new


type SonyProjectorConfigEntry = ConfigEntry[SonyProjectorCoordinator]


class SonyProjectorCoordinator(DataUpdateCoordinator[ProjectorState]):
    """Polls the projector and executes commands on behalf of entities."""

    config_entry: SonyProjectorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SonyProjectorConfigEntry,
        projector: SonyProjectorADCP,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.projector = projector
        self._timer_read_at: Optional[float] = None
        # Changes confirmed by commands while a poll is in flight. Commands
        # interleave with the poll's queries (they share only the protocol
        # lock), so the poll may have read a value from before the command;
        # these are re-applied to its result so a slider does not jump back.
        self._poll_overrides: Optional[dict[str, Any]] = None

    async def _async_update_data(self) -> ProjectorState:
        """Fetch a fresh snapshot, keeping changes made while it ran."""
        self._poll_overrides = {}
        try:
            state = await self._poll()
            return _with_changes(state, self._poll_overrides)
        finally:
            self._poll_overrides = None

    async def _poll(self) -> ProjectorState:
        """Query the projector.

        A failed power query means the projector is unreachable; that fails the
        whole update so entities go unavailable (DataUpdateCoordinator logs the
        transition once each way). A single failed setting query while on keeps
        the previous value -- signal-dependent settings answer err_inactive.
        """
        power_status = await self.projector.get_power_status()
        if power_status is None:
            if self.projector.auth_failed:
                # Starts a reauth flow; see DataUpdateCoordinator.
                raise ConfigEntryAuthFailed(self.projector.describe_last_error())
            raise UpdateFailed(
                f"Projector unreachable: {self.projector.describe_last_error()}"
            )

        previous = self.data
        state = ProjectorState(
            power_status=power_status,
            # Last input is kept while off, as the media player always did.
            source=previous.source if previous else None,
            timer=previous.timer if previous else None,
        )

        if state.is_on:
            old_values = previous.values if previous else {}
            state.source = await self.projector.get_input() or state.source
            blank = await self.projector.get_blank_status()
            state.blank = (
                blank if blank is not None else (previous.blank if previous else None)
            )
            for parameter in STRING_SETTINGS:
                value = await self.projector.get_string_value(parameter)
                if value is None:
                    value = old_values.get(parameter)
                if value is not None:
                    state.values[parameter] = value
            for parameter in NUMERIC_SETTINGS:
                value = await self.projector.get_numeric_value(parameter)
                if value is None:
                    value = old_values.get(parameter)
                if value is not None:
                    state.values[parameter] = value

        now = time.monotonic()
        if self._timer_read_at is None or now - self._timer_read_at >= TIMER_INTERVAL:
            timer = await self.projector.get_timer()
            if timer:
                state.timer = timer
                self._timer_read_at = now

        return state

    # -- commands -------------------------------------------------------------

    def _require(self, result: bool, action: str) -> None:
        """Raise a user-visible error when the projector did not accept a command."""
        if not result:
            raise HomeAssistantError(
                f"Projector could not {action}: "
                f"{self.projector.describe_last_error()}"
            )

    def _patch(self, **changes: Any) -> None:
        """Apply a confirmed change to the snapshot and notify entities.

        Deliberately not async_set_updated_data: that cancels a pending
        debounced refresh (losing the re-read queued by _refresh_soon) and
        reschedules the 30s poll on every slider move.
        """
        if self._poll_overrides is not None:
            for key, value in changes.items():
                if key == "values":
                    self._poll_overrides.setdefault("values", {}).update(value)
                else:
                    self._poll_overrides[key] = value
        if self.data is None:
            return
        self.data = _with_changes(self.data, changes)
        self.async_update_listeners()

    def _refresh_soon(self) -> None:
        """Re-poll in the background after a change with knock-on effects."""
        self.config_entry.async_create_background_task(
            self.hass, self.async_request_refresh(), f"{DOMAIN} refresh"
        )

    async def async_set_power(self, on: bool) -> None:
        """Turn the projector on or off."""
        self._require(
            await self.projector.set_power(on), "turn on" if on else "turn off"
        )
        # Show the transition immediately; the poll reports the real phase.
        self._patch(power_status="startup" if on else "cooling1")
        self._refresh_soon()

    async def async_set_source(self, source: str, label: str) -> None:
        """Switch input."""
        self._require(await self.projector.set_input(source), f"switch to {label}")
        self._patch(source=source)

    async def async_set_blank(self, on: bool) -> None:
        """Mute or unmute the picture."""
        self._require(
            await self.projector.set_blank(on),
            "mute the picture" if on else "unmute the picture",
        )
        self._patch(blank=on)

    async def async_set_string(self, parameter: str, value: str, label: str) -> None:
        """Set a string setting such as picture_mode or aspect."""
        self._require(
            await self.projector.set_string_value(parameter, value),
            f"set {label} to {value}",
        )
        self._patch(values={parameter: value})
        if parameter == "picture_mode":
            # Brightness, contrast etc. are stored per picture mode.
            self._refresh_soon()

    async def async_set_numeric(self, parameter: str, value: int) -> None:
        """Set brightness, contrast or sharpness."""
        self._require(
            await self.projector.set_numeric_value(parameter, value),
            f"set {parameter} to {value}",
        )
        self._patch(values={parameter: value})

    async def async_step_numeric(self, parameter: str, delta: int) -> None:
        """Move a numeric setting by ``delta`` from its current device value.

        Read fresh rather than from the snapshot: it can be up to 30s stale (or
        empty right after a restart), and stepping from a stale or assumed value
        makes the picture jump.
        """
        current = await self.projector.get_numeric_value(parameter)
        if current is None:
            raise HomeAssistantError(
                f"Projector could not read current {parameter}: "
                f"{self.projector.describe_last_error()}"
            )
        await self.async_set_numeric(
            parameter, max(NUMERIC_MIN, min(current + delta, NUMERIC_MAX))
        )

    async def async_send_key(self, key: str) -> None:
        """Send a remote-control key."""
        self._require(await self.projector.send_key(key), f"send key {key}")
        if key == "blank":
            # The key toggles picture mute; re-read so the switch follows.
            self._refresh_soon()

    async def async_send_raw(self, command: str) -> str:
        """Send a raw ADCP command and return the projector's answer."""
        response = await self.projector.send_command(command)
        if response is None:
            raise HomeAssistantError(
                f"Raw command {command!r} failed: "
                f"{self.projector.describe_last_error()}"
            )
        _LOGGER.info("Raw command '%s' returned: %s", command, response)
        return response
