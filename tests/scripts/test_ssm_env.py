import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "ssm_env.py"
_spec = importlib.util.spec_from_file_location("ssm_env", _PATH)
ssm_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssm_env)


def test_parse_env_reads_repo_style_files():
    text = """
# comment
POSTGRES_USER=web3agent
export LOG_LEVEL=INFO
DEEPSEEK_BASE_URL=https://api.deepseek.com
QUOTED='a b c'
DOUBLE="x=y"
EMPTY=
WITH_COMMENT=660  # minutes
"""
    assert ssm_env.parse_env(text) == {
        "POSTGRES_USER": "web3agent",
        "LOG_LEVEL": "INFO",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "QUOTED": "a b c",
        "DOUBLE": "x=y",
        "EMPTY": "",
        "WITH_COMMENT": "660",
    }


def test_parse_env_rejects_malformed_lines():
    with pytest.raises(ValueError, match="line 2"):
        ssm_env.parse_env("A=1\nnot a pair\n")


def test_format_env_quotes_only_when_needed_and_round_trips():
    values = {
        "TOKEN": "abc-DEF_123=",
        "URL": "https://api.deepseek.com/v1",
        "PASSWORD": "p@ss word$HOME#1",
        "EMPTY": "",
    }
    rendered = ssm_env.format_env(values)
    assert "TOKEN=abc-DEF_123=\n" in rendered
    assert "URL=https://api.deepseek.com/v1\n" in rendered
    # Single quotes stop docker compose from expanding $HOME.
    assert "PASSWORD='p@ss word$HOME#1'\n" in rendered
    assert ssm_env.parse_env(rendered) == values


def test_format_env_refuses_values_it_cannot_quote():
    with pytest.raises(ValueError, match="BAD"):
        ssm_env.format_env({"BAD": "it's"})


def test_missing_required_flags_absent_and_empty_values():
    assert ssm_env.missing_required({"POSTGRES_PASSWORD": "x", "CHAT_API_INTERNAL_KEY": ""}) == [
        "CHAT_API_INTERNAL_KEY"
    ]
    assert ssm_env.missing_required({"POSTGRES_PASSWORD": "x", "CHAT_API_INTERNAL_KEY": "y"}) == []
