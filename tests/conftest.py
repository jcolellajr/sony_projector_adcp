"""Shared fixtures."""
import pytest

from custom_components.sony_projector_adcp.const import (
    CONF_USE_AUTH,
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake_projector import FakeProjector


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    yield


@pytest.fixture(autouse=True)
def allow_loopback_sockets(socket_enabled):
    """The fake projector is a real TCP server; the harness still limits
    connections to 127.0.0.1."""
    yield


@pytest.fixture
async def projector():
    """A running fake projector with password authentication."""
    fake = FakeProjector()
    await fake.start()
    yield fake
    await fake.stop()


def entry_for(fake: FakeProjector, password: str = "Projector") -> MockConfigEntry:
    """A config entry pointing at ``fake``."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="127.0.0.1",
        title="Sony Projector",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake.port,
            CONF_NAME: "Sony Projector",
            CONF_USE_AUTH: True,
            CONF_PASSWORD: password,
        },
    )
