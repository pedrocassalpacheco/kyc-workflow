"""AnthropicBackend: the only module that imports the Anthropic SDK.

It is called by `HeliosGateway` and by nothing else. It turns a gateway
request into one Messages API call (structured output when a schema is
given), maps SDK errors to `BackendError` with a transient flag so the
gateway can apply Helios's retry rule, and returns text, parsed output and
token usage. Prompt caching goes on the system block, which is the stable
part of every request.
"""

from __future__ import annotations

from typing import Any

import anthropic
import pydantic
from pydantic import BaseModel

from kyc_workflow.config import load_env
from kyc_workflow.gateway.protocol import BackendError, BackendResult, TokenUsage, ToolCall, ToolDef

ADAPTIVE_THINKING: dict[str, Any] = {"type": "adaptive"}


class AnthropicBackend:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        thinking: dict[str, Any] | None = None,
    ) -> None:
        if client is None:
            load_env()  # ANTHROPIC_API_KEY from .env; the SDK reads it from the environment
            client = anthropic.Anthropic()
        self._client = client
        self._thinking = ADAPTIVE_THINKING if thinking is None else thinking

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDef] | None,
        output_schema: type[BaseModel] | None,
        max_tokens: int,
        metadata_user_id: str,
        effort: str | None = None,
    ) -> BackendResult:
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            metadata={"user_id": metadata_user_id},
            thinking=self._thinking,
        )
        if effort:
            kwargs["output_config"] = {"effort": effort}
        if tools:
            kwargs["tools"] = [t.model_dump() for t in tools]
        try:
            if output_schema is not None:
                message = self._client.messages.parse(output_format=output_schema, **kwargs)
                parsed = message.parsed_output
            else:
                message = self._client.messages.create(**kwargs)
                parsed = None
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as err:
            raise BackendError("connection failure", transient=True, cause=err) from err
        except anthropic.RateLimitError as err:
            raise BackendError("rate limited", transient=True, cause=err) from err
        except anthropic.APIStatusError as err:
            transient = err.status_code >= 500
            raise BackendError(
                f"API status {err.status_code}", transient=transient, cause=err
            ) from err
        except (pydantic.ValidationError, ValueError) as err:
            # The SDK parses structured output on the way back; a truncated reply
            # (max_tokens reached, thinking included) fails here. Content-free on purpose.
            raise BackendError(
                "structured output could not be parsed (truncated at max_tokens?)", transient=False, cause=err
            ) from err

        text = "".join(block.text for block in message.content if block.type == "text")
        tool_calls = [
            ToolCall(id=block.id, name=block.name, input=dict(block.input))
            for block in message.content if block.type == "tool_use"
        ]
        usage = message.usage
        return BackendResult(
            model=message.model,
            text=text,
            parsed=parsed,
            stop_reason=message.stop_reason,
            tool_calls=tool_calls,
            content_blocks=[block.model_dump(mode="json", exclude_none=True) for block in message.content],
            usage=TokenUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            ),
            provider_request_id=message.id,
        )
