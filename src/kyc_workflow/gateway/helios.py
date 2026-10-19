"""HeliosGateway: a simulation of the bank's model gateway.

Helios, as Leo and Ben described it:

- the only sanctioned path to a model; pinned to one Vertex region with no
  failover ("if it drops, it drops, and you retry");
- a model allowlist; adding a model is a change-control matter;
- logs metadata only: caller, timestamp, model, token counts, latency,
  request id. Never prompt or response content. Kept ninety days;
- no redaction and no guardrails of its own;
- tool calling, passed through as the model supports it (assumed to come
  with Claude's approval; today's Gemini path has only the older schema);
- no embeddings, no batch.

This class reproduces that contract in front of any `ModelBackend`. The
workflow is written against it so that swapping in the real Helios is a
backend change, not a workflow change.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from kyc_workflow.config import Settings
from kyc_workflow.gateway.protocol import (
    BackendError,
    GatewayError,
    HeliosRejected,
    HeliosUnavailable,
    HeliosUnsupported,
    ModelBackend,
    ModelRequest,
    ModelResponse,
)

METADATA_LOG_NAME = "helios_metadata.jsonl"


class MetadataEntry(BaseModel):
    """One line of the Helios log. Metadata only, by construction: there is no
    field that could hold prompt or response text."""

    request_id: str
    timestamp: str
    caller_id: str
    case_id: str
    analyst_id: str
    model: str
    region: str
    attempt: int
    status: str  # ok | retry | error | rejected
    tool_count: int = 0  # tools offered on the call; never their names or arguments
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    error_type: str | None = None  # exception class name only


class HeliosGateway:
    def __init__(
        self,
        backend: ModelBackend,
        settings: Settings | None = None,
        *,
        log_path: Path | None = None,
        write_log: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._backend = backend
        self.settings = settings or Settings.from_env()
        self.entries: list[MetadataEntry] = []
        self._log_path = (
            log_path if log_path is not None else self.settings.audit_dir / METADATA_LOG_NAME
        ) if write_log else None
        self._clock = clock
        self._sleep = sleep

    # -- the one supported operation ------------------------------------

    def complete(self, request: ModelRequest) -> ModelResponse:
        request_id = request.request_id or str(uuid.uuid4())
        model = request.model or self.settings.model

        if not request.case_id.strip() or not request.analyst_id.strip():
            self._log(request_id, request, model, 1, "rejected", error_type="MissingMetadata")
            raise HeliosRejected("case_id and analyst_id are required on every call")
        if model not in self.settings.model_allowlist:
            self._log(request_id, request, model, 1, "rejected", error_type="ModelNotAllowed")
            raise HeliosRejected(
                f"model {model!r} is not on the Helios allowlist "
                f"{list(self.settings.model_allowlist)}; adding one is a change-control request"
            )

        metadata_user_id = f"{self.settings.caller_id}/{request.analyst_id}/{request.case_id}"
        attempt = 1
        while True:
            started = self._clock()
            try:
                result = self._backend.complete(
                    model=model,
                    system=request.system,
                    messages=request.conversation(),
                    tools=request.tools,
                    output_schema=request.output_schema,
                    max_tokens=request.max_tokens,
                    metadata_user_id=metadata_user_id,
                    effort=request.effort,
                )
            except BackendError as err:
                latency = (self._clock() - started) * 1000
                if err.transient and attempt <= self.settings.max_retries:
                    self._log(request_id, request, model, attempt, "retry",
                              latency_ms=latency, error_type=type(err.cause or err).__name__)
                    self._sleep(self.settings.retry_backoff_s * (2 ** (attempt - 1)))
                    attempt += 1
                    continue
                self._log(request_id, request, model, attempt, "error",
                          latency_ms=latency, error_type=type(err.cause or err).__name__)
                if err.transient:
                    raise HeliosUnavailable(
                        f"region {self.settings.region} unavailable after {attempt} attempt(s); "
                        "no failover region is configured"
                    ) from err
                raise GatewayError(f"backend rejected the request: {err}") from err

            latency = (self._clock() - started) * 1000
            self._log(request_id, request, model, attempt, "ok",
                      latency_ms=latency, usage=result.usage)
            return ModelResponse(
                request_id=request_id,
                model=result.model,
                text=result.text,
                parsed=result.parsed,
                stop_reason=result.stop_reason,
                usage=result.usage,
                latency_ms=latency,
                attempts=attempt,
                tool_calls=result.tool_calls,
                content_blocks=result.content_blocks,
            )

    # -- things Helios does not offer -----------------------------------

    def embed(self, *_args, **_kwargs):
        raise HeliosUnsupported("embedding models are not on the Helios allowlist")

    def batch(self, *_args, **_kwargs):
        raise HeliosUnsupported("Helios has no batch endpoint")

    # -- metadata log ---------------------------------------------------

    def _log(self, request_id, request: ModelRequest, model, attempt, status, *,
             latency_ms=0.0, usage=None, error_type=None) -> None:
        entry = MetadataEntry(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            caller_id=self.settings.caller_id,
            case_id=request.case_id,
            analyst_id=request.analyst_id,
            model=model,
            region=self.settings.region,
            attempt=attempt,
            status=status,
            tool_count=len(request.tools or []),
            latency_ms=round(latency_ms, 1),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            cache_read_input_tokens=usage.cache_read_input_tokens if usage else 0,
            cache_creation_input_tokens=usage.cache_creation_input_tokens if usage else 0,
            error_type=error_type,
        )
        self.entries.append(entry)
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.model_dump()) + "\n")
