"""DeepSeek-V4.1-Flash is the primary model, with thinking mode on by default."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[2]))

from config.settings import Settings
from src.classifier import llm_gateway
from src.classifier.llm_gateway import DEEPSEEK_REASONING_TOKEN_ALLOWANCE, LLMGateway


class _RecordingClient:
    def __init__(self, finish_reason: str = "stop", content: str = '{"is_relevant": true}'):
        self.calls = []
        self._choice = SimpleNamespace(
            finish_reason=finish_reason, message=SimpleNamespace(content=content)
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[self._choice])


def _gateway_with(provider: str, client: _RecordingClient) -> LLMGateway:
    gateway = LLMGateway.__new__(LLMGateway)
    gateway._clients = {provider: client}
    gateway._model_by_provider = {provider: llm_gateway.PROVIDER_CONFIG[provider]["model"]}
    return gateway


def _call(gateway: LLMGateway, provider: str, max_tokens: int = 300) -> str | None:
    return gateway._call_openai_compatible(
        provider, "system", "user", json_mode=True, temperature=0.1, max_tokens=max_tokens,
    )


def test_deepseek_defaults_to_v4_1_flash_with_thinking(isolated_defaults) -> None:
    settings = Settings()

    assert settings.DEEPSEEK_MODEL == "deepseek-flash"
    assert settings.DEEPSEEK_THINKING is True
    assert settings.LLM_PROVIDER_PRIORITY.split(",")[0] == "deepseek"


def test_thinking_request_reserves_room_for_reasoning_on_top_of_the_answer(monkeypatch) -> None:
    monkeypatch.setattr(llm_gateway.settings, "DEEPSEEK_THINKING", True)
    client = _RecordingClient()

    result = _call(_gateway_with("deepseek", client), "deepseek", max_tokens=300)

    assert result == '{"is_relevant": true}'
    (call,) = client.calls
    assert call["model"] == llm_gateway.PROVIDER_CONFIG["deepseek"]["model"]
    assert call["extra_body"] == {"thinking": {"type": "enabled"}}
    # Reasoning counts against max_tokens; the caller's 300 stay for the answer.
    assert call["max_tokens"] == 300 + DEEPSEEK_REASONING_TOKEN_ALLOWANCE
    assert call["response_format"] == {"type": "json_object"}


def test_thinking_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setattr(llm_gateway.settings, "DEEPSEEK_THINKING", False)
    client = _RecordingClient()

    _call(_gateway_with("deepseek", client), "deepseek", max_tokens=300)

    (call,) = client.calls
    assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert call["max_tokens"] == 300


def test_fallback_providers_get_neither_the_thinking_field_nor_the_allowance(monkeypatch) -> None:
    monkeypatch.setattr(llm_gateway.settings, "DEEPSEEK_THINKING", True)
    client = _RecordingClient()

    _call(_gateway_with("qwen", client), "qwen", max_tokens=300)

    (call,) = client.calls
    assert "extra_body" not in call
    assert call["max_tokens"] == 300


def test_running_out_of_max_tokens_is_logged(caplog) -> None:
    client = _RecordingClient(finish_reason="length", content="")

    with caplog.at_level("WARNING", logger=llm_gateway.logger.name):
        result = _call(_gateway_with("deepseek", client), "deepseek")

    assert result == ""
    assert "hit max_tokens" in caplog.text
