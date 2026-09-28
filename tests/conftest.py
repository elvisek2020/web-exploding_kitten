import asyncio
import inspect
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# main.py připojuje "static" a herní logika čte balíček relativně k rootu repa
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import main  # noqa: E402
import harness  # noqa: E402


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Spouští `async def` testy bez pluginu (pytest-asyncio apod.)."""
    if inspect.iscoroutinefunction(pyfuncitem.obj):
        params = inspect.signature(pyfuncitem.obj).parameters
        kwargs = {name: pyfuncitem.funcargs[name] for name in params}
        asyncio.run(pyfuncitem.obj(**kwargs))
        return True
    return None


@pytest.fixture(autouse=True)
def fresh_server(monkeypatch):
    """Každý test začíná s prázdným serverem a výchozí konfigurací."""
    for state in (
        main.lobbies, main.connected_clients, main.player_last_activity,
        main.disconnected_at, main.player_registry, main.token_map, main.ip_connections,
    ):
        state.clear()
    monkeypatch.setattr(main, "rate_limiter", main.RateLimiter(10_000))
    monkeypatch.setattr(main, "admin_login_throttle", main.LoginThrottle(3, 900))
    monkeypatch.setattr(main, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", [])
    monkeypatch.setattr(main, "DISCONNECT_GRACE_SECONDS", 15)
    harness.reset()
    yield
