"""
@file llm.py
@description OpenAI-compatible LLM client adapter with disk-backed prompt-hash caching and cost tracking
@module sqldoctor/agent/llm
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class LLMToolCall(BaseModel):
    """Tool call emitted by LLM."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", description="Unique identifier for the tool call")
    type: str = Field(default="function", description="Type of call")
    function_name: str = Field(description="Name of the function called")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Parsed arguments")


class LLMMessage(BaseModel):
    """Single message in a conversational LLM exchange."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(description="Message role: system, user, assistant, or tool")
    content: str | None = Field(default=None, description="Text content of message")
    name: str | None = Field(default=None, description="Tool name if role is tool or function")
    tool_call_id: str | None = Field(
        default=None, description="Tool call ID if answering a tool call"
    )
    tool_calls: list[LLMToolCall] | None = Field(
        default=None, description="Tool calls issued by assistant"
    )


class LLMUsage(BaseModel):
    """Token usage and cost tracking."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)


class LLMResponse(BaseModel):
    """Standardized response from LLM."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None)
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    finish_reason: str = Field(default="stop")
    usage: LLMUsage = Field(default_factory=LLMUsage)
    cached: bool = Field(default=False)
    prompt_hash: str = Field(default="")


class LLMClient:
    """Client for OpenAI-compatible LLM endpoints with prompt caching and cost enforcement."""

    # Default pricing per million tokens (approx Gemini Flash tier)
    DEFAULT_INPUT_COST_PER_M = 0.075
    DEFAULT_OUTPUT_COST_PER_M = 0.30

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "gemini-3.1-flash-lite",
        cache_dir: Path | str = "cache/llm",
        max_cost_usd: float = 1.00,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        ).rstrip("/")
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_cost_usd = max_cost_usd
        self.timeout_seconds = timeout_seconds
        self.cumulative_cost_usd = 0.0

    def compute_prompt_hash(
        self,
        messages: Sequence[LLMMessage | dict[str, Any]],
        model: str,
        temperature: float,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Compute deterministic SHA-256 hash of request payload.

        Args:
            messages: List of chat messages.
            model: Model identifier.
            temperature: Sampling temperature.
            tools: Tool definitions.

        Returns:
            Hex string digest.
        """
        raw_msgs = [
            m.model_dump(exclude_none=True) if isinstance(m, LLMMessage) else m for m in messages
        ]
        serialized = json.dumps(
            {
                "model": model,
                "temperature": round(temperature, 4),
                "messages": raw_msgs,
                "tools": tools or [],
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate call cost in USD from token counts."""
        cost = (prompt_tokens / 1_000_000.0) * self.DEFAULT_INPUT_COST_PER_M + (
            completion_tokens / 1_000_000.0
        ) * self.DEFAULT_OUTPUT_COST_PER_M
        return round(cost, 6)

    def generate(
        self,
        messages: Sequence[LLMMessage | dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Execute chat completion with cache check and cost tracking.

        Args:
            messages: Conversation messages.
            tools: Optional tool definitions in OpenAI schema.
            temperature: Sampling temperature.

        Returns:
            LLMResponse object.

        Raises:
            RuntimeError: If cost cap is exceeded or remote API call fails.
        """
        p_hash = self.compute_prompt_hash(messages, self.model, temperature, tools)
        cache_file = self.cache_dir / f"{p_hash}.json"

        # 1. Check prompt cache first
        if cache_file.is_file():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    cached_data = json.load(f)
                cached_data["cached"] = True
                cached_data["prompt_hash"] = p_hash
                return LLMResponse.model_validate(cached_data)
            except Exception as e:
                logger.warning("Failed reading cache file %s: %s; refreshing...", cache_file, e)

        # 2. Check cost cap before remote network call
        if self.cumulative_cost_usd >= self.max_cost_usd:
            raise RuntimeError(
                f"LLM cost cap of ${self.max_cost_usd:.2f} exceeded. Current: ${self.cumulative_cost_usd:.4f}"
            )

        if not self.api_key:
            raise ValueError("No API key provided for LLM client and prompt is not in disk cache.")

        # 3. Format OpenAI-compatible chat completion payload
        formatted_msgs = []
        for m in messages:
            if isinstance(m, LLMMessage):
                formatted_msgs.append(m.model_dump(exclude_none=True))
            else:
                formatted_msgs.append(m)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_msgs,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self.base_url}/chat/completions"

        response = None
        for attempt in range(3):
            try:
                response = requests.post(
                    endpoint, headers=headers, json=payload, timeout=self.timeout_seconds
                )
                if response.status_code == 200:
                    break
                elif response.status_code in (429, 503) and tools and attempt == 0:
                    # If tool calling encounters capacity spike on free tier, retry without tools payload
                    logger.info(
                        "Tool calling encountered %d; retrying in text-prompt mode...",
                        response.status_code,
                    )
                    payload.pop("tools", None)
                    continue
                elif response.status_code in (429, 503):
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                if attempt < 2:
                    import time

                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise

        if response is None or response.status_code != 200:
            status = response.status_code if response else "NO_RESPONSE"
            text = response.text if response else "Request timed out or failed to connect"
            raise RuntimeError(f"LLM API request failed [{status}]: {text}")

        resp_json = response.json()
        choice = resp_json.get("choices", [{}])[0]
        message_data = choice.get("message", {})
        raw_tool_calls = message_data.get("tool_calls", [])

        parsed_tool_calls: list[LLMToolCall] = []
        for tc in raw_tool_calls:
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {"raw": raw_args}
            else:
                args = raw_args
            parsed_tool_calls.append(
                LLMToolCall(
                    id=tc.get("id", f"call_{len(parsed_tool_calls)}"),
                    type=tc.get("type", "function"),
                    function_name=func.get("name", ""),
                    arguments=args,
                )
            )

        usage_data = resp_json.get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)
        call_cost = self._estimate_cost(prompt_tokens, completion_tokens)
        self.cumulative_cost_usd += call_cost

        llm_resp = LLMResponse(
            content=message_data.get("content"),
            tool_calls=parsed_tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=call_cost,
            ),
            cached=False,
            prompt_hash=p_hash,
        )

        # 4. Save to cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(llm_resp.model_dump(), f, indent=2)
        except Exception as e:
            logger.warning("Failed writing to cache file %s: %s", cache_file, e)

        return llm_resp
