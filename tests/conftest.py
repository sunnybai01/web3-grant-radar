"""Shared test fixtures.

config.settings calls load_dotenv() at import time, which pushes the developer's
.env values into os.environ. Tests that assert *documented defaults* were
therefore order- and machine-dependent: monkeypatch.delenv() only removes what the
test explicitly names, so any other .env key leaked in and flipped assertions
(SOCIAL_WATCH_INTERVAL_MINUTES, DAILY_SUMMARY_ENABLED, ...).

`isolated_defaults` removes every key that the repo .env files define so the
defaults under test are genuinely the code defaults.
"""
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))

_ENV_FILES = (REPO_ROOT / ".env", REPO_ROOT / ".env.example")
_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _keys_declared_in_env_files() -> set[str]:
    keys: set[str] = set()
    for path in _ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = _KEY_RE.match(line)
            if match:
                keys.add(match.group(1))
    return keys


@pytest.fixture
def isolated_defaults(monkeypatch):
    """Drop every env key the repo .env files define, so code defaults apply."""
    for key in _keys_declared_in_env_files():
        monkeypatch.delenv(key, raising=False)
    yield
