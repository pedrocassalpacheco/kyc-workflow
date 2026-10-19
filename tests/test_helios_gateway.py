"""HeliosGateway behaviour, offline: allowlist, metadata, retries, log."""

import json

import pytest
from pydantic import BaseModel

from kyc_workflow.gateway import (
    BackendError,
    FakeBackend,
    GatewayError,
    HeliosGateway,
    HeliosRejected,
    HeliosUnavailable,
    HeliosUnsupported,
    MetadataEntry,
)
from tests.conftest import SECRET_ANSWER, SECRET_SYSTEM, SECRET_USER


class Answer(BaseModel):
    doc_date: str


# -- happy path ------------------------------------------------------------

def test_passes_request_through_and_returns_backend_result(make_gateway, make_request, ok_result):
    backend = FakeBackend([ok_result(parsed=Answer(doc_date="2026-07-24"))])
    gw = make_gateway(backend)

    resp = gw.complete(make_request(output_schema=Answer, request_id="req-1"))

    assert resp.request_id == "req-1"
    assert resp.text == SECRET_ANSWER
    assert resp.parsed == Answer(doc_date="2026-07-24")
    assert resp.usage.cache_read_input_tokens == 100
    assert resp.attempts == 1
    call = backend.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["system"] == SECRET_SYSTEM
    assert call["messages"] == [{"role": "user", "content": SECRET_USER}]
    assert call["output_schema"] is Answer


def test_generates_request_id_when_absent(make_gateway, make_request, ok_result):
    gw = make_gateway(FakeBackend([ok_result()]))
    resp = gw.complete(make_request())
    assert resp.request_id and len(resp.request_id) >= 32


def test_analyst_and_case_travel_as_metadata(make_gateway, make_request, ok_result):
    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend)
    gw.complete(make_request(case_id="VGB-C-088410", analyst_id="AN-007"))
    assert backend.calls[0]["metadata_user_id"] == "harness-test/AN-007/VGB-C-088410"


# -- Helios policy ---------------------------------------------------------

@pytest.mark.parametrize("field", ["case_id", "analyst_id"])
def test_rejects_calls_without_case_or_analyst(make_gateway, make_request, ok_result, field):
    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend)
    with pytest.raises(HeliosRejected):
        gw.complete(make_request(**{field: "  "}))
    assert backend.calls == []
    assert gw.entries[-1].status == "rejected"


def test_rejects_model_not_on_allowlist(make_gateway, make_request, ok_result):
    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend)
    with pytest.raises(HeliosRejected, match="allowlist"):
        gw.complete(make_request(model="claude-opus-5-5"))
    assert backend.calls == []


def test_allowlist_can_be_extended_through_settings(make_gateway, make_request, ok_result):
    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend, model_allowlist=("claude-sonnet-4-6", "claude-haiku-5-5"))
    gw.complete(make_request(model="claude-haiku-5-5"))
    assert backend.calls[0]["model"] == "claude-haiku-5-5"


def test_unsupported_features_are_refused(make_gateway, make_request):
    gw = make_gateway()
    with pytest.raises(HeliosUnsupported):
        gw.embed(["x"])
    with pytest.raises(HeliosUnsupported):
        gw.batch([])


def test_tools_pass_through_one_per_turn(make_gateway, make_request, ok_result):
    from kyc_workflow.gateway import ToolDef

    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend)
    tool = ToolDef(name="get_customer", description="d", input_schema={"type": "object", "properties": {}})
    gw.complete(make_request(tools=[tool]))
    assert backend.calls[0]["tools"] == [tool]
    assert gw.entries[-1].tool_count == 1


def test_conversation_form_is_passed_as_messages(make_gateway, make_request, ok_result):
    backend = FakeBackend([ok_result()])
    gw = make_gateway(backend)
    history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": [{"type": "text", "text": "a"}]},
               {"role": "user", "content": "q2"}]
    gw.complete(make_request(user=None, messages=history))
    assert backend.calls[0]["messages"] == history


# -- fail then retry, no failover ------------------------------------------

def test_retries_transient_failure_then_succeeds(make_gateway, make_request, ok_result):
    backend = FakeBackend([
        BackendError("boom", transient=True, cause=ConnectionError()),
        ok_result(),
    ])
    gw = make_gateway(backend)
    resp = gw.complete(make_request())
    assert resp.attempts == 2
    assert len(backend.calls) == 2
    assert gw.sleeps == [0.1]
    assert [e.status for e in gw.entries] == ["retry", "ok"]
    assert gw.entries[0].error_type == "ConnectionError"


def test_gives_up_after_max_retries_with_no_failover(make_gateway, make_request):
    backend = FakeBackend([BackendError("boom", transient=True)] * 5)
    gw = make_gateway(backend, max_retries=2)
    with pytest.raises(HeliosUnavailable, match="no failover"):
        gw.complete(make_request())
    assert len(backend.calls) == 3  # first try plus two retries
    assert gw.sleeps == [0.1, 0.2]  # backoff doubles
    assert [e.status for e in gw.entries] == ["retry", "retry", "error"]


def test_permanent_failure_is_not_retried(make_gateway, make_request):
    backend = FakeBackend([BackendError("bad request", transient=False)])
    gw = make_gateway(backend)
    with pytest.raises(GatewayError) as excinfo:
        gw.complete(make_request())
    assert not isinstance(excinfo.value, HeliosUnavailable)
    assert len(backend.calls) == 1
    assert gw.sleeps == []


# -- metadata-only log -------------------------------------------------------

def test_log_holds_metadata_and_never_content(make_gateway, make_request, ok_result, log_path):
    backend = FakeBackend([
        BackendError("boom", transient=True, cause=TimeoutError()),
        ok_result(),
    ])
    gw = make_gateway(backend)
    gw.complete(make_request(request_id="trace-42"))

    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    ok = json.loads(lines[1])
    assert ok["request_id"] == "trace-42"
    assert ok["caller_id"] == "harness-test"
    assert ok["case_id"] == "PR-88214" and ok["analyst_id"] == "AN-SAM"
    assert ok["model"] == "claude-sonnet-4-6" and ok["region"] == "asia-southeast1"
    assert ok["status"] == "ok" and ok["attempt"] == 2
    assert ok["input_tokens"] == 120 and ok["output_tokens"] == 30
    assert ok["cache_read_input_tokens"] == 100
    assert "timestamp" in ok and "latency_ms" in ok

    raw = log_path.read_text()
    for marker in ("SYSTEM-PROMPT-MARKER", "USER-CONTENT-MARKER", "ANSWER-MARKER"):
        assert marker not in raw


def test_metadata_entry_has_no_field_for_content():
    fields = set(MetadataEntry.model_fields)
    for forbidden in ("system", "user", "prompt", "text", "response", "content", "parsed"):
        assert forbidden not in fields


def test_log_file_defaults_to_audit_dir(make_settings, make_request, ok_result, tmp_path):
    gw = HeliosGateway(FakeBackend([ok_result()]), make_settings(audit_dir=tmp_path / "audit"))
    gw.complete(make_request())
    assert (tmp_path / "audit" / "helios_metadata.jsonl").exists()
