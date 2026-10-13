"""Self-built thin LLM Gateway — DeepSeek first, Qwen/Gemini as optional fallbacks.

Uses OpenAI-compatible SDK for DeepSeek and Qwen, and Google genai SDK for Gemini.
Supports automatic fallback through the configured provider priority list; a
provider without an API key is skipped.
"""
import logging
import json
from typing import Optional, Dict, Any

from openai import OpenAI

from config.settings import settings

logger = logging.getLogger(__name__)

# Per-request timeout and retry budget. The SDK defaults (600s, 3 attempts) let a
# single hung provider block the sequential item loop for ~30 minutes.
LLM_TIMEOUT_SECONDS = settings.LLM_TIMEOUT_SECONDS
LLM_MAX_RETRIES = settings.LLM_MAX_RETRIES

# With thinking on, DeepSeek counts the reasoning against max_tokens: at
# max_tokens=100 it spent all 100 on reasoning and returned no answer. Callers'
# max_tokens is the budget for the answer, so reasoning gets this on top. Only
# tokens actually generated are billed; classification calls reasoned 0.7-2.9k.
DEEPSEEK_REASONING_TOKEN_ALLOWANCE = 8192

# ---------------------------------------------------------------------------
# Provider registry — each entry produces an OpenAI-compatible client + model id
# ---------------------------------------------------------------------------

PROVIDER_CONFIG = {
    "deepseek": {
        "api_key": lambda: settings.DEEPSEEK_API_KEY,
        "base_url": lambda: settings.DEEPSEEK_BASE_URL,
        "model": settings.DEEPSEEK_MODEL,
        "create_client": lambda: OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        ),
        # Sent explicitly either way, so a change of the API default cannot
        # silently flip the mode.
        "extra_body": lambda: {
            "thinking": {"type": "enabled" if settings.DEEPSEEK_THINKING else "disabled"}
        },
        "reasoning_allowance": lambda: (
            DEEPSEEK_REASONING_TOKEN_ALLOWANCE if settings.DEEPSEEK_THINKING else 0
        ),
    },
    "qwen": {
        "api_key": lambda: settings.QWEN_API_KEY,
        "base_url": lambda: settings.QWEN_BASE_URL,
        "model": settings.QWEN_MODEL,
        "create_client": lambda: OpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url=settings.QWEN_BASE_URL,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        ),
    },
    "gemini": {
        "api_key": lambda: settings.GEMINI_API_KEY,
        "base_url": lambda: settings.GEMINI_BASE_URL,
        "model": settings.GEMINI_MODEL,
        "create_client": lambda: None,  # Gemini uses different SDK path
    },
}

# Parse priority order
PROVIDER_PRIORITY = [
    p.strip()
    for p in settings.LLM_PROVIDER_PRIORITY.split(",")
    if p.strip() in PROVIDER_CONFIG
]


class LLMGateway:
    """Unified LLM caller with automatic fallback across providers."""

    def __init__(self):
        self._clients: Dict[str, Any] = {}
        self._model_by_provider: Dict[str, str] = {}
        for name, cfg in PROVIDER_CONFIG.items():
            api_key = cfg["api_key"]()
            if not api_key:
                continue
            client = self._init_gemini(api_key) if name == "gemini" else cfg["create_client"]()
            if client is None:
                # Storing a None client made `if not self._clients` never fire and
                # deferred the breakage to call time.
                logger.warning("LLM provider '%s' is configured but unusable — skipped", name)
                continue
            self._clients[name] = client
            self._model_by_provider[name] = cfg["model"]

        if not self._clients:
            logger.warning("No LLM providers configured — LLM gateway will fail!")

    def _init_gemini(self, api_key: str):
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            return genai
        except ImportError:
            logger.error("google-generativeai not installed")
            return None

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """Send a chat completion, falling back through providers on failure.

        Returns the model's text response, or None if all providers fail.
        """
        for provider_name in PROVIDER_PRIORITY:
            if provider_name not in self._clients:
                continue

            try:
                if provider_name == "gemini":
                    result = self._call_gemini(
                        provider_name, system_prompt, user_prompt,
                        json_mode, temperature, max_tokens,
                    )
                else:
                    result = self._call_openai_compatible(
                        provider_name, system_prompt, user_prompt,
                        json_mode, temperature, max_tokens,
                    )

                if result:
                    self.last_provider = provider_name
                    self.last_model = self._model_by_provider.get(provider_name)
                    return result

                logger.warning("LLM provider '%s' returned an empty response", provider_name)

            except Exception as e:
                logger.warning(f"LLM provider '{provider_name}' failed: {e}")
                continue

        logger.error("All LLM providers exhausted — returning None")
        return None

    def _call_openai_compatible(
        self, provider: str, system: str, user: str,
        json_mode: bool, temperature: float, max_tokens: int,
    ) -> Optional[str]:
        client = self._clients[provider]
        cfg = PROVIDER_CONFIG[provider]
        model = cfg["model"]
        reasoning_allowance = cfg["reasoning_allowance"]() if "reasoning_allowance" in cfg else 0

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens + reasoning_allowance,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        if "extra_body" in cfg:
            kwargs["extra_body"] = cfg["extra_body"]()

        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            # Otherwise indistinguishable from an empty reply: the reasoning
            # or the answer ran out of max_tokens.
            logger.warning(
                "LLM provider '%s' hit max_tokens=%s; the answer is truncated or missing",
                provider, kwargs["max_tokens"],
            )
        return choice.message.content

    def _call_gemini(
        self, provider: str, system: str, user: str,
        json_mode: bool, temperature: float, max_tokens: int,
    ) -> Optional[str]:
        genai = self._clients[provider]
        model_id = PROVIDER_CONFIG[provider]["model"]

        model = genai.GenerativeModel(
            model_id,
            system_instruction=system,
        )

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }

        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        resp = model.generate_content(
            user,
            generation_config=genai.GenerationConfig(**generation_config),
        )
        return resp.text

    def classify_structured(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """Call LLM with JSON mode and parse the result into a dict.

        Returns None if the output is unparseable.
        """
        raw = self.complete(system_prompt, user_prompt, json_mode=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"LLM returned invalid JSON: {raw[:200]}")
            return None
