"""Protocol-level behaviour against the fake projector."""
import pytest

from custom_components.sony_projector_adcp.protocol import (
    CannotConnect,
    InvalidAuth,
    SonyProjectorADCP,
)

from .fake_projector import FakeProjector


async def _closed_port() -> int:
    fake = FakeProjector()
    await fake.start()
    port = fake.port
    await fake.stop()
    return port


async def test_auth_success(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    await adcp.validate()
    assert await adcp.get_power_status() == "standby"
    assert adcp.auth_failed is False
    await adcp.disconnect()


async def test_nokey_projector_needs_no_password():
    fake = FakeProjector(password=None)
    await fake.start()
    try:
        adcp = SonyProjectorADCP("127.0.0.1", fake.port, "anything")
        assert await adcp.get_power_status() == "standby"
        await adcp.disconnect()
    finally:
        await fake.stop()


async def test_bad_password_raises_invalid_auth(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "wrong")
    with pytest.raises(InvalidAuth):
        await adcp.validate()
    assert adcp.auth_failed is True


async def test_bad_password_during_poll_sets_flags(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "wrong")
    assert await adcp.get_power_status() is None
    assert adcp.auth_failed is True
    assert adcp.describe_last_error() == "authentication failed"


async def test_unreachable_raises_cannot_connect():
    adcp = SonyProjectorADCP("127.0.0.1", await _closed_port(), "Projector")
    with pytest.raises(CannotConnect):
        await adcp.validate()
    assert adcp.auth_failed is False
    assert await adcp.get_power_status() is None
    assert adcp.describe_last_error() == "cannot connect to projector"


async def test_rejection_is_described(projector):
    projector.responses['power "on"'] = "err_inactive"
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    assert await adcp.set_power(True) is False
    assert "cooling down" in adcp.describe_last_error()
    assert "(err_inactive)" in adcp.describe_last_error()
    await adcp.disconnect()


async def test_unknown_error_code_is_shown_raw(projector):
    projector.responses['power "on"'] = "err_internal1"
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    assert await adcp.set_power(True) is False
    assert adcp.describe_last_error() == "err_internal1"
    await adcp.disconnect()


async def test_success_clears_last_error(projector):
    projector.responses['power "on"'] = "err_inactive"
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    assert await adcp.set_power(True) is False
    assert await adcp.set_power(False) is True
    assert adcp.last_error is None
    await adcp.disconnect()


async def test_survives_idle_disconnect(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    assert await adcp.get_power_status() == "standby"
    projector.drop_sessions()
    assert await adcp.get_power_status() == "standby"
    await adcp.disconnect()


async def test_timer_is_flattened(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "Projector")
    assert await adcp.get_timer() == {
        "operation": 128,
        "light_src": 123,
        "prev_light_src": 0,
    }
    await adcp.disconnect()


async def test_auth_disabled_but_required_is_invalid_auth(projector):
    """use_auth off against a password-protected projector must not 'connect'."""
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "", use_auth=False)
    with pytest.raises(InvalidAuth):
        await adcp.validate()


async def test_unreachable_after_rejection_reports_unreachable(projector):
    adcp = SonyProjectorADCP("127.0.0.1", projector.port, "wrong")
    assert await adcp.get_power_status() is None
    assert adcp.describe_last_error() == "authentication failed"
    adcp.port = await _closed_port()
    assert await adcp.get_power_status() is None
    assert adcp.describe_last_error() == "cannot connect to projector"
