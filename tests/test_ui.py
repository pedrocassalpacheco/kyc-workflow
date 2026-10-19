"""The web UI's API over the real chat session, MCP client (in-process) and a fake model."""

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from kyc_workflow.config import BankApiSettings, Settings
from kyc_workflow.gateway import FakeGateway, ModelResponse, TokenUsage, ToolCall
from kyc_workflow.ui import UIState, create_app, read_results
from kyc_workflow.ui.app import Bus
from tests.conftest import BANK_API_KEY


def scripted(*turns):
    turns = list(turns)
    return FakeGateway(lambda req: turns.pop(0))


def tool_turn(name, **arguments):
    call = ToolCall(id=f"toolu_{name}", name=name, input=arguments)
    return ModelResponse(request_id="r1", model="fake", text="", stop_reason="tool_use", tool_calls=[call],
                         usage=TokenUsage(input_tokens=100, output_tokens=10),
                         content_blocks=[{"type": "tool_use", "id": call.id, "name": name, "input": arguments}])


def text_turn(text):
    return ModelResponse(request_id="r2", model="fake", text=text, stop_reason="end_turn",
                         usage=TokenUsage(input_tokens=100, output_tokens=10), content_blocks=[{"type": "text", "text": text}])


@pytest.fixture
def results(tmp_path: Path) -> dict[str, Path]:
    routing = tmp_path / "routing"; routing.mkdir()
    (routing / "20261019T141931Z_claude-haiku-5-5.json").write_text(json.dumps({"model": "m", "mean": 0.933, "exact": 14, "cases": [{}] * 15}))
    (routing / "20261019T143436Z_claude-haiku-5-5.json").write_text(json.dumps({"model": "m", "mean": 1.0, "exact": 15, "cases": [{}] * 15}))
    guard = tmp_path / "guardrails" / "20261019T151038Z"; guard.mkdir(parents=True)
    (guard / "report.json").write_text(json.dumps({"model": "m", "pass_rate": 0.93, "passed": 14, "total": 15,
                                                   "judge": {"model": "j", "calls": 25, "input_tokens": 25177, "output_tokens": 8419}}))
    (tmp_path / "guardrails" / "broken").mkdir()
    (tmp_path / "guardrails" / "broken" / "report.json").write_text("not json")
    return {"routing": routing, "guardrails": tmp_path / "guardrails"}


@pytest.fixture
def client(bank_api_url, results, tmp_path):
    gateway = scripted(tool_turn("list_accounts", customer_ref="CIF-1000001"),
                       text_turn("One account, 0001234567 (accounts)."))
    settings = Settings(model="fake-model", model_allowlist=("fake-model",), audit_dir=tmp_path / "audit")

    async def fake_eval(name, run):
        state.bus.publish("eval", {"name": name, "line": "ok  1.00 case-a"})
        run.update(status="passed", exit_code=0, summary="1/1 cases exact")
        state.bus.publish("eval", {"name": name, "status": "passed", "exit_code": 0, "summary": run["summary"]})

    state = UIState(gateway=gateway, settings=settings, records_target="inproc",
                    bank_api=BankApiSettings(url=bank_api_url, api_key=BANK_API_KEY),
                    use_guard_llm=False, results_dirs=results, eval_runner=fake_eval)
    with TestClient(create_app(state)) as c:
        yield c


def test_index_and_static(client):
    assert "VGB records" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_status_reflects_the_live_session(client):
    s = client.get("/api/status").json()
    assert s["model"] == "fake-model" and s["guard_model"] is None
    assert len(s["tools"]) == 15 and s["mcp"] == "inproc"
    assert s["session_id"] and s["turns"] == 0 and s["busy"] is False
    from kyc_workflow.chat import EXAMPLE_QUESTIONS
    assert s["examples"] == EXAMPLE_QUESTIONS and len(EXAMPLE_QUESTIONS) >= 5


def test_chat_ask_runs_the_real_session_and_reports_the_turn(client):
    r = client.post("/api/chat/ask", json={"text": "Which accounts does CIF-1000001 hold?"})
    assert r.status_code == 200
    d = r.json()
    assert d["reply"].startswith("One account")
    assert d["turn"]["outcome"] == "answered" and d["turn"]["tool_calls"] == 1 and d["turn"]["model_calls"] == 2
    assert d["turn"]["input_tokens"] == 200 and d["turn"]["output_tokens"] == 20

    h = client.get("/api/chat/history").json()["messages"]
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert client.get("/api/status").json()["totals"]["tool_calls"] == 1


def test_blocked_message_and_empty_message(client):
    r = client.post("/api/chat/ask", json={"text": "Close the file for CIF-1000001."})
    assert r.json()["turn"]["outcome"] == "refused"
    assert client.post("/api/chat/ask", json={"text": "  "}).status_code == 400


def test_new_session_resets_turns(client):
    client.post("/api/chat/ask", json={"text": "Close the file."})
    old = client.get("/api/status").json()["session_id"]
    r = client.post("/api/chat/new")
    assert r.status_code == 200 and r.json()["session_id"] != old
    assert client.get("/api/status").json()["turns"] == 0


def test_eval_history_reads_results_from_disk(results):
    h = {name: read_results(name, path) for name, path in results.items()}
    assert [r["score"] for r in h["routing"]] == [0.933, 1.0]
    assert h["routing"][0]["at"] == "2026-10-19T14:19:31+00:00" and h["routing"][0]["total"] == 15
    assert len(h["guardrails"]) == 1  # the broken report is skipped
    assert h["guardrails"][0]["judge"]["input_tokens"] == 25177


def test_eval_run_endpoint_and_unknown_eval(client):
    assert client.post("/api/evals/run", json={"name": "nope"}).status_code == 400
    d = client.post("/api/evals/run", json={"name": "routing"}).json()
    assert d["status"] == "running"
    import time
    for _ in range(50):
        s = client.get("/api/status").json()["evals"]["routing"]
        if s["status"] != "running":
            break
        time.sleep(0.05)
    assert s["status"] == "passed" and s["summary"] == "1/1 cases exact"


@pytest.mark.anyio
async def test_bus_fans_out_and_keeps_history():
    import asyncio

    bus = Bus(history=3)
    bus.bind(asyncio.get_running_loop())
    q = bus.subscribe()
    for i in range(4):
        bus.publish("log", {"line": f"l{i}"})
    assert [m["line"] for m in bus.history] == ["l1", "l2", "l3"]
    assert (await q.get())["line"] == "l0"
    before = q.qsize()
    bus.unsubscribe(q)
    bus.publish("log", {"line": "after"})
    assert q.qsize() == before  # nothing is delivered after unsubscribing


# -- workflow -----------------------------------------------------------------------------

@pytest.fixture
def wf_client(bank_api_url, results, tmp_path):
    from tests.test_workflow import fake_model

    settings = Settings(model="fake-model", model_allowlist=("fake-model",), audit_dir=tmp_path / "audit")
    state = UIState(gateway=FakeGateway(fake_model), settings=settings, records_target="inproc",
                    bank_api=BankApiSettings(url=bank_api_url, api_key=BANK_API_KEY), use_guard_llm=False, results_dirs=results)
    with TestClient(create_app(state)) as c:
        yield c


def _wait_pack(client, review, tries=100):
    import time
    for _ in range(tries):
        d = client.get(f"/api/workflow/pack/{review}").json()
        if d["status"] != "running":
            return d
        time.sleep(0.05)
    raise AssertionError("pack did not finish")


def test_workflow_builds_a_pack_and_checks_it(wf_client):
    assert wf_client.get("/api/workflow/reviews").json()["reviews"]
    r = wf_client.post("/api/workflow/pack", json={"review_id": "VGB-PR-2026-0001", "use_model": True})
    assert r.status_code == 200 and r.json()["status"] == "running"
    d = _wait_pack(wf_client, "VGB-PR-2026-0001")
    assert d["status"] == "done" and d["exceptions"] >= 3 and d["model_calls"] == 6
    assert d["steps"]["documents"]["status"] == "done" and d["steps"]["documents"]["model_step"] is True
    assert d["pack"]["recorded_outcome"] == "unchanged" and "## Exceptions" in d["markdown"]
    assert wf_client.get("/api/status").json()["packs"]["VGB-PR-2026-0001"]["status"] == "done"

    c = wf_client.post("/api/workflow/check", json={"review_id": "VGB-PR-2026-0001", "recorded_outcome": "unchanged",
                                                   "clauses": ["4.3"], "rationale": "Rating confirmed, nothing of note.", "use_model": False})
    assert c.status_code == 200
    codes = {f["code"] for f in c.json()["check"]["flags"]}
    assert "CONFIRMED_OVER_UNRESOLVED_HIT" in codes and c.json()["check"]["clean"] is False
    assert "flag(s)" in c.json()["check_markdown"]
    assert wf_client.get("/api/workflow/pack/VGB-PR-2026-0001").json()["check"]["clean"] is False


def test_workflow_document_and_errors(wf_client):
    assert "COMPLETION ACCOUNT" in wf_client.get("/api/document/1000001_sof_letter_1.txt").json()["text"]
    assert wf_client.get("/api/document/nope.txt").status_code == 404
    assert wf_client.get("/api/workflow/pack/VGB-PR-2099-0000").status_code == 404
    assert wf_client.post("/api/workflow/check", json={"review_id": "VGB-PR-2099-0000"}).status_code == 404
    wf_client.post("/api/workflow/pack", json={"review_id": "VGB-PR-2099-9999", "use_model": False})
    d = _wait_pack(wf_client, "VGB-PR-2099-9999")
    assert d["status"] == "error" and "neither on the worklist" in d["error"]
