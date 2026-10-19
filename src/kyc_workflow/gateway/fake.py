"""Test doubles.

`FakeBackend` sits behind a real `HeliosGateway` so gateway behaviour
(allowlist, retries, metadata log) is tested with no network.
`FakeGateway` replaces the whole gateway for workflow-step tests that only
need canned model answers.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from kyc_workflow.gateway.protocol import (
    BackendResult,
    ModelRequest,
    ModelResponse,
    TokenUsage,
)


class FakeBackend:
    """Returns scripted results in order. An Exception in the script is raised."""

    def __init__(self, script: list[BackendResult | Exception] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> BackendResult:
        self.calls.append(kwargs)
        if not self.script:
            return BackendResult(model=kwargs["model"], text="ok", usage=TokenUsage(input_tokens=1, output_tokens=1))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeGateway:
    """A `ModelGateway` that answers from a function of the request."""

    def __init__(
        self,
        responder: Callable[[ModelRequest], ModelResponse | BaseModel | str] | None = None,
    ) -> None:
        self._responder = responder or (lambda req: "ok")
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        answer = self._responder(request)
        if isinstance(answer, ModelResponse):
            return answer
        parsed = answer if isinstance(answer, BaseModel) else None
        text = answer.model_dump_json() if isinstance(answer, BaseModel) else str(answer)
        return ModelResponse(
            request_id=request.request_id or f"fake-{len(self.requests)}",
            model=request.model or "fake-model",
            text=text,
            parsed=parsed,
            stop_reason="end_turn",
            content_blocks=[{"type": "text", "text": text}],
        )
