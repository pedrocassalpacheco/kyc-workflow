"""A chat session end to end with a scripted model: real MCP tools over the
real bank HTTP server (fixture export), real guardrails, real audit log.
Only the model is fake."""

import json
from pathlib import Path

import pytest

from kyc_workflow.chat import ChatSession, Guardrails, Intent, IntentResult, RecordsClient
from kyc_workflow.config import BankApiSettings, Settings
from kyc_workflow.gateway import FakeGateway, ModelRequest, ModelResponse, TokenUsage, ToolCall
from tests.conftest import BANK_API_KEY

pytestmark = pytest.mark.anyio


USAGE = TokenUsage(input_tokens=100, output_tokens=10)


def tool_turn(name: str, **arguments) -> ModelResponse:
    call = ToolCall(id=f"toolu_{name}", name=name, input=arguments)
    return ModelResponse(
        request_id=f"req-{name}", model="fake", text="", stop_reason="tool_use", tool_calls=[call], usage=USAGE,
        content_blocks=[{"type": "tool_use", "id": call.id, "name": name, "input": arguments}],
    )


def text_turn(text: str) -> ModelResponse:
    return ModelResponse(request_id="req-text", model="fake", text=text, stop_reason="end_turn", usage=USAGE,
                         content_blocks=[{"type": "text", "text": text}])


class Script:
    """Answers in order, and remembers every request it saw."""

    def __init__(self, *turns: ModelResponse):
        self.turns = list(turns)
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.turns.pop(0)


@pytest.fixture
async def toolbox(bank_api_url):
    """The MCP client over an in-process server (memory transport) so the test
    needs no second process; the protocol path is the same as over HTTP."""
    async with RecordsClient("inproc", BankApiSettings(url=bank_api_url, api_key=BANK_API_KEY)) as rc:
        yield rc


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(model="fake-model", model_allowlist=("fake-model",), audit_dir=tmp_path / "audit")


def events_of(session: ChatSession, kind: str) -> list[dict]:
    return [e for e in session.events if e["event"] == kind]


async def test_two_tool_rounds_then_answer_with_full_audit_trail(toolbox, settings):
    script = Script(
        tool_turn("get_customer", customer_ref="CIF-1000001"),
        tool_turn("list_accounts", customer_ref="CIF-1000001"),
        text_turn("Tan Mei Ling (customers, CIF-1000001) holds one account, 0001234567 (accounts), status OPEN."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings, analyst_id="AN-TEST")

    reply = await session.ask("Who is CIF-1000001 and what accounts do they hold?")

    assert reply.startswith("Tan Mei Ling")
    # the model saw the tools and the growing conversation
    assert len(script.requests) == 3
    assert {t.name for t in script.requests[0].tools} == toolbox.names
    assert script.requests[0].case_id == session.case_id and script.requests[0].analyst_id == "AN-TEST"
    assert [len(r.messages) for r in script.requests] == [1, 3, 5]
    tool_result_turn = script.requests[1].messages[2]
    assert tool_result_turn["role"] == "user"
    assert tool_result_turn["content"][0]["type"] == "tool_result"
    assert '"legal_name": "Tan Mei Ling"' in tool_result_turn["content"][0]["content"]

    kinds = [e["event"] for e in session.events]
    assert kinds == [
        "session_start", "user_message", "guardrail_input",
        "model_call", "guardrail_tool_call", "tool_result",
        "model_call", "guardrail_tool_call", "tool_result",
        "model_call", "guardrail_output", "assistant_message", "turn_end",
    ]
    end = events_of(session, "turn_end")[0]
    assert end["outcome"] == "answered"
    assert end["model_calls"] == 3 and end["tool_calls"] == 2
    assert end["input_tokens"] == 300 and end["output_tokens"] == 30   # three gateway calls at 100/10 each
    assert end["session_totals"] == {"model_calls": 3, "tool_calls": 2, "input_tokens": 300, "output_tokens": 30}
    assert session.last_turn["turn"] == 1 and "duration_ms" in end
    results = events_of(session, "tool_result")
    assert [r["tool"] for r in results] == ["get_customer", "list_accounts"]
    assert all(r["bank_request_ids"] for r in results)  # traceable to the bank's api log
    assert events_of(session, "guardrail_output")[0]["tools_used"] == 2

    lines = Path(session.log_path).read_text().splitlines()
    assert len(lines) == len(session.events)
    assert json.loads(lines[-1])["event"] == "turn_end"
    assert json.loads(lines[-2])["text"].startswith("Tan Mei Ling")


async def test_several_tool_calls_in_one_turn_run_and_return_in_order(toolbox, settings):
    calls = [ToolCall(id="toolu_a", name="get_customer", input={"customer_ref": "CIF-1000001"}),
             ToolCall(id="toolu_b", name="list_accounts", input={"customer_ref": "CIF-1000001"}),
             ToolCall(id="toolu_c", name="list_screening_hits", input={"customer_ref": "CIF-1000001"})]
    parallel = ModelResponse(
        request_id="req-par", model="fake", text="", stop_reason="tool_use", tool_calls=calls,
        content_blocks=[{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls],
    )
    script = Script(parallel, text_turn("Tan Mei Ling: one account, two screening hits (customers, accounts, screening_hits)."))
    session = ChatSession(FakeGateway(script), toolbox, settings)

    reply = await session.ask("Everything on CIF-1000001, please.")

    assert reply.startswith("Tan Mei Ling")
    results = script.requests[1].messages[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_a", "toolu_b", "toolu_c"]
    assert all(r["type"] == "tool_result" and not r["is_error"] for r in results)
    assert [e["tool"] for e in events_of(session, "tool_result")] == ["get_customer", "list_accounts", "list_screening_hits"] or \
        len(events_of(session, "tool_result")) == 3  # logged as they finish; all three present
    assert events_of(session, "guardrail_output")[0]["tools_used"] == 3


async def test_history_keeps_only_guarded_turns(toolbox, settings):
    script = Script(
        tool_turn("get_customer", customer_ref="CIF-1000001"),
        text_turn("Tan Mei Ling is recorded (customers, CIF-1000001)."),
        text_turn("Nothing more on file."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    await session.ask("Who is CIF-1000001?")
    assert [m["role"] for m in session.history] == ["user", "assistant", "user", "assistant"]
    assert session.history[-1] == {"role": "assistant",
                                   "content": [{"type": "text", "text": "Tan Mei Ling is recorded (customers, CIF-1000001)."}]}
    assert session.history[1]["content"][0]["type"] == "tool_use"      # tool rounds stay, with their results
    assert session.history[2]["content"][0]["type"] == "tool_result"

    await session.ask("Anything else?")
    roles = [m["role"] for m in script.requests[-1].messages]
    assert roles == ["user", "assistant", "user", "assistant", "user"]


async def test_withheld_reply_is_replaced_in_history_before_the_next_turn(toolbox, settings):
    script = Script(
        text_turn("The customer should be rated as low risk; the file can be closed."),
        text_turn("Understood."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    await session.ask("Thoughts on CIF-1000001?")
    await session.ask("OK.")
    seen = script.requests[-1].messages
    assert seen[1]["role"] == "assistant"
    assert seen[1]["content"][0]["text"].startswith("[guardrail] The reply was withheld")
    assert "rated as low risk" not in json.dumps(seen)


async def test_unsourced_warning_is_what_the_history_keeps(toolbox, settings):
    long_claim = ("The customer was onboarded in 2004 and holds one account with a declared turnover of "
                  "180,000; the rating on file is 2 and there are two screening hits.")
    script = Script(text_turn(long_claim), text_turn("Noted."))
    session = ChatSession(FakeGateway(script), toolbox, settings)
    reply = await session.ask("Tell me about CIF-1000001 from memory.")
    assert reply.startswith("[guardrail: no record was consulted")
    await session.ask("Thanks.")
    assert script.requests[-1].messages[1]["content"][0]["text"] == reply


async def test_round_budget_leaves_history_consistent_for_the_next_turn(toolbox, settings):
    script = Script(*[tool_turn("list_transaction_files") for _ in range(5)], text_turn("Fine."))
    guard = Guardrails(allowed_tools=toolbox.names, max_tool_rounds=1)
    session = ChatSession(FakeGateway(script), toolbox, settings, guardrails=guard)
    reply = await session.ask("Keep listing files.")
    assert "Stopped after 1 tool rounds" in reply
    assert session.history[-1] == {"role": "assistant", "content": [{"type": "text", "text": reply}]}
    await session.ask("And now?")
    roles = [m["role"] for m in script.requests[-1].messages]
    assert all(a != b for a, b in zip(roles, roles[1:]))  # roles alternate, never two users in a row
    assert roles[-1] == "user"


async def test_every_turn_ends_with_turn_end_and_totals_accumulate(toolbox, settings):
    script = Script(
        text_turn("The customer should be rated as low risk."),           # turn 2: withheld
        tool_turn("get_customer", customer_ref="CIF-1000001"),            # turn 3: answered
        text_turn("Tan Mei Ling (customers, CIF-1000001)."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    await session.ask("Close the file.")                                   # turn 1: refused, no model call
    await session.ask("Thoughts?")
    await session.ask("Who is CIF-1000001?")

    ends = events_of(session, "turn_end")
    assert [e["turn"] for e in ends] == [1, 2, 3]
    assert [e["outcome"] for e in ends] == ["refused", "withheld", "answered"]
    assert [e["model_calls"] for e in ends] == [0, 1, 2]
    assert [e["input_tokens"] for e in ends] == [0, 100, 200]
    assert ends[-1]["session_totals"] == {"model_calls": 3, "tool_calls": 1, "input_tokens": 300, "output_tokens": 30}
    assert session.totals == ends[-1]["session_totals"]


async def test_intent_classifier_call_is_counted_and_logged(toolbox, settings):
    def classify(text):
        return IntentResult(intent=Intent(category="read_records", reason="lookup"), model="guard",
                            request_id="req-guard", input_tokens=40, output_tokens=8, latency_ms=120)

    guard = Guardrails(allowed_tools=toolbox.names, intent_classifier=classify)
    script = Script(text_turn("Which customer?"))
    session = ChatSession(FakeGateway(script), toolbox, settings, guardrails=guard)
    await session.ask("Show me a record.")

    gi = events_of(session, "guardrail_input")[0]
    assert gi["model_call"]["request_id"] == "req-guard" and gi["model_call"]["category"] == "read_records"
    end = events_of(session, "turn_end")[0]
    assert end["model_calls"] == 2                       # classifier plus the reply
    assert end["input_tokens"] == 140 and end["output_tokens"] == 18


async def test_gateway_outage_still_ends_the_turn(toolbox, settings):
    from kyc_workflow.gateway import HeliosUnavailable

    def down(_request):
        raise HeliosUnavailable("region unavailable")

    session = ChatSession(FakeGateway(down), toolbox, settings)
    await session.ask("Who is CIF-1000001?")
    end = events_of(session, "turn_end")[0]
    assert end["outcome"] == "error" and end["model_calls"] == 0 and end["input_tokens"] == 0


async def test_cancelling_a_turn_rolls_back_history_and_logs_it(toolbox, settings):
    import asyncio

    script = Script(tool_turn("get_customer", customer_ref="CIF-1000001"), text_turn("Tan Mei Ling."))
    session = ChatSession(FakeGateway(script), toolbox, settings)

    async def slow_call(name, arguments):  # the analyst hits Ctrl+C while the tool is running
        await asyncio.sleep(10)

    toolbox.call = slow_call  # type: ignore[method-assign]
    try:
        turn = asyncio.ensure_future(session.ask("Who is CIF-1000001?"))
        await asyncio.sleep(0.05)
        assert len(session.history) == 2  # user turn and the model's tool-use turn are in flight
        turn.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turn
    finally:
        del toolbox.call  # restore the class method for other tests

    assert session.history == []
    assert events_of(session, "turn_cancelled")[0]["history_entries_dropped"] == 2
    end = events_of(session, "turn_end")[0]
    assert end["outcome"] == "cancelled" and end["model_calls"] == 1

    await session.ask("Who is CIF-1000001?")  # the session is still usable afterwards
    assert session.history[-1]["content"][0]["text"] == "Tan Mei Ling."


async def test_blocked_user_message_never_reaches_the_model(toolbox, settings):
    script = Script()
    session = ChatSession(FakeGateway(script), toolbox, settings)
    reply = await session.ask("Close the file for CIF-1000001.")
    assert "cannot close" in reply
    assert script.requests == []
    assert events_of(session, "guardrail_input")[0]["rule"] == "write_or_close"
    assert session.history == []


async def test_reply_recommending_a_rating_is_withheld_and_logged(toolbox, settings):
    script = Script(
        tool_turn("get_customer", customer_ref="CIF-1000001"),
        text_turn("The customer should be rated as low risk; the file can be closed."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    reply = await session.ask("Look at CIF-1000001 for me.")
    assert reply.startswith("[guardrail] The reply was withheld")
    last = events_of(session, "assistant_message")[0]
    assert last["withheld"] is True and "rated as low risk" in last["original_text"]


async def test_disallowed_tool_is_refused_as_a_tool_error(toolbox, settings):
    script = Script(
        tool_turn("close_case", case_id="CM-1"),
        text_turn("I cannot do that; which record do you want?"),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    await session.ask("Look into CM-1.")
    blocked = events_of(session, "guardrail_tool_call")[0]
    assert blocked["allowed"] is False and blocked["rule"] == "tool_not_allowed"
    error_result = script.requests[1].messages[2]["content"][0]
    assert error_result["is_error"] is True and "guardrail" in error_result["content"]
    assert events_of(session, "tool_result") == []  # never reached the MCP server


async def test_tool_error_from_the_server_is_passed_back_as_error(toolbox, settings):
    script = Script(
        tool_turn("get_customer", customer_ref="CIF-0000000"),
        text_turn("Not found in file: there is no customer CIF-0000000."),
    )
    session = ChatSession(FakeGateway(script), toolbox, settings)
    reply = await session.ask("Who is CIF-0000000?")
    assert reply.startswith("Not found in file")
    assert events_of(session, "tool_result")[0]["is_error"] is True
    assert script.requests[1].messages[2]["content"][0]["is_error"] is True


async def test_round_budget_stops_a_looping_model(toolbox, settings):
    script = Script(*[tool_turn("list_transaction_files") for _ in range(10)])
    guard = Guardrails(allowed_tools=toolbox.names, max_tool_rounds=2)
    session = ChatSession(FakeGateway(script), toolbox, settings, guardrails=guard)
    reply = await session.ask("Keep listing files.")
    assert "Stopped after 2 tool rounds" in reply
    assert len(script.requests) == 3  # initial call plus two rounds


async def test_gateway_failure_is_reported_not_raised(toolbox, settings):
    from kyc_workflow.gateway import HeliosUnavailable

    def down(_request):
        raise HeliosUnavailable("region asia-southeast1 unavailable")

    session = ChatSession(FakeGateway(down), toolbox, settings)
    reply = await session.ask("Who is CIF-1000001?")
    assert "unavailable" in reply
    assert events_of(session, "model_error")[0]["error_type"] == "HeliosUnavailable"
    assert session.history == []


# -- the log lines ---------------------------------------------------------------------

def test_format_event_surfaces_stop_reason_and_loop_decision():
    import logging

    from kyc_workflow.chat.session import format_event

    level, line = format_event({
        "event": "model_call", "turn": 3, "request_id": "abcdef12-0000", "model": "m", "stop_reason": "tool_use",
        "attempts": 1, "latency_ms": 812.4, "usage": {"input_tokens": 400, "output_tokens": 40, "cache_read_input_tokens": 300},
        "tool_calls": [{"name": "get_customer", "arguments": {"customer_ref": "CIF-1"}}], "text_chars": 0,
    })
    assert level == logging.INFO
    assert "turn 3 model_call stop_reason=tool_use in=400 out=40 cache_read=300 812ms" in line
    assert "-> run 1 tool(s): get_customer(customer_ref='CIF-1')" in line

    level, line = format_event({
        "event": "model_call", "turn": 3, "request_id": "abcdef12", "model": "m", "stop_reason": "end_turn",
        "attempts": 2, "latency_ms": 10, "usage": {"input_tokens": 1, "output_tokens": 1}, "tool_calls": [], "text_chars": 50,
    })
    assert level == logging.INFO and line.endswith("-> final answer") and "attempts=2" in line

    level, line = format_event({
        "event": "model_call", "turn": 1, "request_id": "x", "model": "m", "stop_reason": "max_tokens",
        "attempts": 1, "latency_ms": 10, "usage": {"input_tokens": 1, "output_tokens": 1}, "tool_calls": [], "text_chars": 50,
    })
    assert level == logging.WARNING and "stop_reason=max_tokens" in line


def test_blocked_and_withheld_events_log_at_warning():
    import logging

    from kyc_workflow.chat.session import format_event

    level, line = format_event({"event": "guardrail_input", "turn": 1, "allowed": False, "rule": "write_or_close",
                                "reason": "matched", "flags": [], "model_call": None})
    assert level == logging.WARNING and "BLOCKED rule=write_or_close" in line
    level, line = format_event({"event": "guardrail_tool_call", "turn": 1, "tool": "close_case", "round": 1,
                                "allowed": False, "rule": "tool_not_allowed", "reason": "no", "flags": [], "model_call": None})
    assert level == logging.WARNING and "close_case round=1 BLOCKED" in line
    level, line = format_event({"event": "tool_result", "turn": 1, "tool": "get_document", "is_error": False, "chars": 10,
                                "latency_ms": 5, "flags": ["injection_suspected"], "bank_request_ids": ["r"], "result_preview": "x"})
    assert level == logging.WARNING and "flags=['injection_suspected']" in line
    level, line = format_event({"event": "assistant_message", "turn": 1, "withheld": True, "original_text": "The file can be closed.", "text": "n"})
    assert level == logging.WARNING and "WITHHELD" in line


async def test_session_narrates_every_event_to_the_logger(toolbox, settings, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="kyc_workflow.chat")
    script = Script(tool_turn("get_customer", customer_ref="CIF-1000001"), text_turn("Tan Mei Ling (customers)."))
    session = ChatSession(FakeGateway(script), toolbox, settings)
    await session.ask("Who is CIF-1000001?")

    lines = [r.getMessage() for r in caplog.records if r.name == "kyc_workflow.chat"]
    assert len(lines) == len(session.events)
    assert any("stop_reason=tool_use" in l and "-> run 1 tool(s): get_customer" in l for l in lines)
    assert any("stop_reason=end_turn" in l and "-> final answer" in l for l in lines)
    assert any(l.startswith("turn 1 tool_result get_customer ok") for l in lines)
    assert any(l.startswith("turn 1 end outcome=answered") for l in lines)


async def test_max_tokens_reply_is_flagged_and_annotated(toolbox, settings):
    cut = ModelResponse(request_id="r", model="fake", text="The customer holds", stop_reason="max_tokens", usage=USAGE,
                        content_blocks=[{"type": "text", "text": "The customer holds"}])
    session = ChatSession(FakeGateway(Script(cut)), toolbox, settings)
    reply = await session.ask("Who is CIF-1000001?")
    assert reply.endswith("[guardrail: the reply was cut off at the model's token limit]")
    assert "truncated" in events_of(session, "guardrail_output")[0]["flags"]
