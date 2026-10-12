"""Route tests exercise route behaviour, not auth.

Auth fails closed, so a route test that calls the API without a key would get a
503. Every test here runs with the key dependency satisfied, except tests marked
``real_auth`` (tests/chat_api/test_auth.py), which exercise the real check.
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.chat_api.app import app
from src.chat_api.auth import verify_internal_key


def pytest_configure(config):
    config.addinivalue_line("markers", "real_auth: run with the real internal-key check")


@pytest.fixture(autouse=True)
def _internal_key_satisfied(request):
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    app.dependency_overrides[verify_internal_key] = lambda: None
    try:
        yield
    finally:
        app.dependency_overrides.pop(verify_internal_key, None)
