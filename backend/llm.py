"""LLM provider transport for the CI assessment enrichment path.

The only concrete implementation is ``OpenAIStructuredLLM``, which uses
the OpenAI SDK's ``AsyncOpenAI`` client with forced tool_use so that
outputs are structurally validated by the model's own JSON schema.

The ``openai`` package is an *optional* dependency (``pip install '.[llm]'``).
Importing this module at the top level is safe even when the package is absent;
the ``ModuleNotFoundError`` is converted to ``LLMUnavailable`` lazily, inside
``OpenAIStructuredLLM.__init__``.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .errors import ProjectHealthError


class LLMUnavailable(ProjectHealthError):
    """The LLM provider was unreachable, misconfigured, or returned unusable output."""


class StructuredLLM(Protocol):
    """Minimal interface for a provider that calls a single named tool and returns its input."""

    async def call_tool(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        model: str,
        max_tokens: int,
    ) -> dict[str, Any]: ...


def _to_openai_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic-style tool dict to OpenAI's function-calling format.

    Anthropic uses ``input_schema`` for the JSON schema; OpenAI uses
    ``parameters`` nested inside a ``function`` wrapper.
    """
    schema = tool.get("input_schema", tool.get("parameters", {}))
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": schema,
        },
    }


class OpenAIStructuredLLM:
    """OpenAI SDK implementation of ``StructuredLLM``.

    Uses forced ``tool_choice`` so the model must call exactly the named tool,
    and ``temperature=0`` for deterministic output.

    Args:
        api_key: OpenAI API key (``PHI_OPENAI_API_KEY``).
        timeout_s: Per-request timeout in seconds. Defaults to 20 s for weekly
            assessments; use a higher value (≤120 s) for spec decomposition.
        max_retries: SDK-level retry count on transient network errors.
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 20.0,
        max_retries: int = 1,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ModuleNotFoundError as exc:
            raise LLMUnavailable(
                "openai SDK is not installed; run: pip install 'app-dev-horizon[llm]'"
            ) from exc
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_s,
            max_retries=max_retries,
        )

    async def call_tool(
        self,
        *,
        system: str,
        user: str,
        tool: dict[str, Any],
        model: str,
        max_tokens: int = 2_048,
    ) -> dict[str, Any]:
        """Call the provider and return the tool's argument dict.

        Raises:
            LLMUnavailable: On any provider error, timeout, or if the model
                does not call the required tool.
        """
        tool_name = tool["name"]
        openai_tool = _to_openai_tool(tool)
        try:
            response = await self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=[openai_tool],
                tool_choice={"type": "function", "function": {"name": tool_name}},
            )
        except Exception as exc:
            raise LLMUnavailable(str(exc)) from exc

        choice = response.choices[0] if response.choices else None
        tool_calls = getattr(getattr(choice, "message", None), "tool_calls", None) or []
        for tc in tool_calls:
            if getattr(getattr(tc, "function", None), "name", None) == tool_name:
                try:
                    return json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError) as exc:
                    raise LLMUnavailable(
                        f"model returned invalid JSON for tool '{tool_name}'"
                    ) from exc

        raise LLMUnavailable(
            f"model did not call the required tool '{tool_name}'"
        )


# Keep the old name as an alias so any direct references still resolve.
AnthropicStructuredLLM = OpenAIStructuredLLM
