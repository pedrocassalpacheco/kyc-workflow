"""AnthropicBackend against a mock HTTP transport: the real SDK request path,
no network. Checks what goes on the wire and how errors are classified."""

import json

import anthropic
import httpx2
import pytest
from anthropic import Anthropic, DefaultHttpxClient
from pydantic import BaseModel

from kyc_workflow.gateway import BackendError
from kyc_workflow.gateway.anthropic_backend import AnthropicBackend


class Extracted(BaseModel):
    document_date: str
    independent: bool


def message_json(text: str, model: str = "claude-sonnet-4-6") -> dict:
    return {
        "id": "msg_test_1",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": text},
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 240,
            "output_tokens": 18,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 0,
        },
    }


@pytest.fixture
def make_backend():
    """AnthropicBackend whose SDK client talks to an in-process mock transport.
    Returns the backend and the list of HTTP requests it sent."""

    def _make(handler):
        seen: list[httpx2.Request] = []

        def wrapped(req: httpx2.Request) -> httpx2.Response:
            seen.append(req)
            return handler(req)

        client = Anthropic(
            api_key="test-key",
            http_client=DefaultHttpxClient(transport=httpx2.MockTransport(wrapped)),
            max_retries=0,
        )
        return AnthropicBackend(client), seen

    return _make


def complete(backend: AnthropicBackend, **overrides):
    kwargs = dict(
        model="claude-sonnet-4-6",
        system="POLICY TEXT",
        messages=[{"role": "user", "content": "CASE MATERIAL"}],
        tools=None,
        output_schema=None,
        max_tokens=512,
        metadata_user_id="harness/AN-1/PR-1",
    )
    kwargs.update(overrides)
    return backend.complete(**kwargs)


def test_effort_goes_in_output_config_only_when_set(make_backend):
    backend, seen = make_backend(lambda r: httpx2.Response(200, json=message_json("x")))
    complete(backend)
    assert "output_config" not in json.loads(seen[0].content)
    complete(backend, effort="medium")
    assert json.loads(seen[1].content)["output_config"] == {"effort": "medium"}


def test_request_shape_on_the_wire(make_backend):
    backend, seen = make_backend(lambda r: httpx2.Response(200, json=message_json("plain answer")))
    result = complete(backend)

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/messages"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["max_tokens"] == 512
    assert body["system"] == [
        {"type": "text", "text": "POLICY TEXT", "cache_control": {"type": "ephemeral"}}
    ]
    assert body["messages"] == [{"role": "user", "content": "CASE MATERIAL"}]
    assert body["metadata"] == {"user_id": "harness/AN-1/PR-1"}
    assert body["thinking"] == {"type": "adaptive"}
    assert "tools" not in body and "tool_choice" not in body

    assert result.text == "plain answer"
    assert result.parsed is None
    assert result.usage.input_tokens == 240
    assert result.usage.cache_read_input_tokens == 200
    assert result.provider_request_id == "msg_test_1"


def test_structured_output_is_requested_and_parsed(make_backend):
    payload = json.dumps({"document_date": "2026-07-24", "independent": True})
    backend, seen = make_backend(lambda r: httpx2.Response(200, json=message_json(payload)))

    result = complete(backend, output_schema=Extracted)

    body = json.loads(seen[0].content)
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert set(fmt["schema"]["properties"]) == {"document_date", "independent"}
    assert result.parsed == Extracted(document_date="2026-07-24", independent=True)


def test_connection_failure_is_transient(make_backend):
    def refuse(req):
        raise httpx2.ConnectError("refused")

    backend, _ = make_backend(refuse)
    with pytest.raises(BackendError) as excinfo:
        complete(backend)
    assert excinfo.value.transient is True
    assert isinstance(excinfo.value.cause, anthropic.APIConnectionError)


@pytest.mark.parametrize(
    "status, transient",
    [(429, True), (500, True), (529, True), (400, False), (401, False), (404, False)],
)
def test_status_codes_are_classified(make_backend, status, transient):
    backend, _ = make_backend(
        lambda r: httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "m"}})
    )
    with pytest.raises(BackendError) as excinfo:
        complete(backend)
    assert excinfo.value.transient is transient


def test_truncated_structured_output_is_a_content_free_backend_error(make_backend):
    truncated = message_json('{"document_date')  # cut off: max_tokens reached mid-JSON
    truncated["stop_reason"] = "max_tokens"
    backend, _ = make_backend(lambda r: httpx2.Response(200, json=truncated))
    with pytest.raises(BackendError) as excinfo:
        complete(backend, output_schema=Extracted)
    assert excinfo.value.transient is False
    assert "document_date" not in str(excinfo.value)


def test_error_messages_do_not_carry_content(make_backend):
    backend, _ = make_backend(
        lambda r: httpx2.Response(400, json={"type": "error", "error": {"type": "x", "message": "m"}})
    )
    with pytest.raises(BackendError) as excinfo:
        complete(backend, system="SECRET-SYSTEM", messages=[{"role": "user", "content": "SECRET-USER"}])
    assert "SECRET" not in str(excinfo.value)


def test_tools_go_on_the_wire_unchanged(make_backend):
    from kyc_workflow.gateway import ToolDef

    reply = message_json("")
    reply["content"] = [{"type": "tool_use", "id": "toolu_1", "name": "get_customer", "input": {"customer_ref": "CIF-1"}}]
    reply["stop_reason"] = "tool_use"
    backend, seen = make_backend(lambda r: httpx2.Response(200, json=reply))
    tool = ToolDef(name="get_customer", description="The customer record.",
                   input_schema={"type": "object", "properties": {"customer_ref": {"type": "string"}}})

    result = complete(backend, tools=[tool])

    body = json.loads(seen[0].content)
    assert body["tools"] == [tool.model_dump()]
    assert "tool_choice" not in body  # passed through as the model supports it, nothing forced or restricted
    assert result.stop_reason == "tool_use"
    assert [tc.model_dump() for tc in result.tool_calls] == [{"id": "toolu_1", "name": "get_customer", "input": {"customer_ref": "CIF-1"}}]
    assert result.content_blocks == [{"type": "tool_use", "id": "toolu_1", "name": "get_customer", "input": {"customer_ref": "CIF-1"}}]
