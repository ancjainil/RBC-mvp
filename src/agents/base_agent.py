"""Abstract base class for all fraud detection agents.

Every concrete agent inherits from ``BaseAgent``, which handles:
- LLM client construction (OpenAI or Anthropic, based on config)
- Prompt loading from ``agent_config.yaml``
- Structured JSON output parsing with retry logic
- Timing and structured logging
- Custom exception hierarchy
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

import structlog
import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import get_settings

logger = structlog.get_logger(__name__)

_settings = get_settings()


# ── Exceptions ────────────────────────────────────────────────────────────


class AgentError(Exception):
    """Base exception for all agent errors."""


class LLMParseError(AgentError):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class LLMCallError(AgentError):
    """Raised when the LLM API call fails after retries."""


# ── LLM factory ──────────────────────────────────────────────────────────


def _build_llm(
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> BaseChatModel:
    """Construct a LangChain chat model from the active provider config.

    Args:
        temperature: Sampling temperature (0 = deterministic).
        max_tokens: Maximum output token count.

    Returns:
        An initialised ``BaseChatModel`` instance.

    Raises:
        AgentError: If the configured provider is not supported.
    """
    provider = _settings.llm.provider

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=_settings.llm.openai_agent_model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=_settings.llm.openai_api_key,  # type: ignore[arg-type]
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=_settings.llm.anthropic_agent_model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=_settings.llm.anthropic_api_key,  # type: ignore[arg-type]
        )

    raise AgentError(f"Unsupported LLM provider: {provider!r}")


# ── Config loader ─────────────────────────────────────────────────────────


def _load_agent_config() -> dict[str, Any]:
    """Load and parse ``config/agent_config.yaml`` once at module import."""
    with open("config/agent_config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_AGENT_CONFIG: dict[str, Any] = _load_agent_config()


# ── Base agent ────────────────────────────────────────────────────────────


class BaseAgent(ABC):
    """Abstract base for all fraud detection agents.

    Subclasses must implement :meth:`_config_key` (to point at their
    section in ``agent_config.yaml``) and provide concrete analysis
    methods.
    """

    def __init__(self) -> None:
        cfg = _AGENT_CONFIG.get(self._config_key, {})
        self._llm: BaseChatModel = _build_llm(
            temperature=cfg.get("model_temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 1024),
        )
        self._prompt_template: str = cfg.get("prompt", "")
        self._cfg: dict[str, Any] = cfg
        self._log = structlog.get_logger(self.__class__.__name__)

    # ── Subclass contract ──────────────────────────────────────────────

    @property
    @abstractmethod
    def _config_key(self) -> str:
        """Key in ``agent_config.yaml`` for this agent's configuration."""

    # ── LLM call helpers ──────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(LLMCallError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Invoke the LLM and return the raw string response.

        Args:
            system_prompt: The system instruction message.
            user_prompt: The user / task message containing transaction data.

        Returns:
            Raw text response from the LLM.

        Raises:
            LLMCallError: If the API call fails.
        """
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        try:
            t0 = time.monotonic()
            response = await self._llm.ainvoke(messages)
            elapsed = (time.monotonic() - t0) * 1000
            self._log.debug(
                "llm.call.complete",
                elapsed_ms=round(elapsed, 2),
                tokens=getattr(response, "usage_metadata", None),
            )
            return str(response.content)
        except Exception as exc:
            self._log.warning("llm.call.failed", error=str(exc))
            raise LLMCallError(f"LLM call failed: {exc}") from exc

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        """Extract and parse a JSON object from the LLM response.

        The LLM sometimes wraps JSON in markdown code fences; this strips
        them before parsing.

        Args:
            raw: Raw LLM response string.

        Returns:
            Parsed JSON dict.

        Raises:
            LLMParseError: If the response does not contain valid JSON.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove opening ```json or ``` line and closing ``` line
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            cleaned = "\n".join(inner)

        # Find the first { and last } to handle preamble text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise LLMParseError(
                f"No JSON object found in LLM response: {raw[:200]!r}"
            )

        json_str = cleaned[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise LLMParseError(
                f"Failed to parse LLM JSON response: {exc}\nRaw: {json_str[:300]!r}"
            ) from exc

    def _format_prompt(self, template: str, **kwargs: Any) -> str:
        """Safely format a prompt template with keyword arguments.

        Uses ``str.format_map`` so that missing keys raise ``KeyError``
        rather than silently leaving placeholders.

        Args:
            template: The prompt template string.
            **kwargs: Values to substitute.

        Returns:
            Formatted prompt string.
        """
        try:
            return template.format_map(kwargs)
        except KeyError as exc:
            self._log.error("prompt.format.missing_key", key=str(exc))
            raise AgentError(f"Missing prompt template key: {exc}") from exc
