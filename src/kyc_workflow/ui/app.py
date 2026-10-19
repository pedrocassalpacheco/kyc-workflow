"""Single-page web UI: chat, workflow slot, evals, with live log and cost panes.

Starlette serves one HTML page and a small JSON API. Everything live goes
over one server-sent events stream:

  log    a line from the kyc_workflow loggers (the same narration as the CLI)
  event  a chat audit event (stop reasons, tool calls, guardrail verdicts, turn costs)
  eval   a line of output from an eval run, and its start/finish
  usage  running totals for the chat session

The chat uses the same ChatSession, guardrails, gateway and MCP client as
`make chat`; the UI is a view on them, not a second implementation. Evals
run as subprocesses of the same `evals.*.run` modules and their results are
read back from the results folders, so history is whatever is on disk.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from kyc_workflow.chat import EXAMPLE_QUESTIONS, ChatSession, Guardrails, RecordsClient, make_intent_classifier
from kyc_workflow.config import PROJECT_ROOT, BankApiSettings, McpSettings, Settings
from kyc_workflow.gateway import HeliosGateway, ModelGateway
from kyc_workflow.workflow import LoadError, build_check, build_pack, check_markdown, pack_markdown

log = logging.getLogger("kyc_workflow.ui")
STATIC = Path(__file__).parent / "static"
EVALS = {"routing": PROJECT_ROOT / "evals" / "routing" / "results",
         "guardrails": PROJECT_ROOT / "evals" / "guardrails" / "results",
         "pack": PROJECT_ROOT / "evals" / "pack" / "results"}

# Reviews worth demonstrating: completed low/medium reviews with documents on file.
DEMO_REVIEWS = ["VGB-PR-2026-1173", "VGB-PR-2026-1037", "VGB-PR-2026-7311", "VGB-PR-2026-7964", "VGB-PR-2026-0156",
                "PR2026-0014", "VGB-PR-2026-9711", "VGB-PR-2026-3331"]


# -- event bus ----------------------------------------------------------------------

class Bus:
    """Fan-out of messages to every open SSE stream. Thread-safe publish."""

    def __init__(self, history: int = 400) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.history: deque[dict] = deque(maxlen=history)

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, kind: str, payload: dict[str, Any]) -> None:
        msg = {"kind": kind, "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **payload}
        if self._loop is None or self._loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._put(msg)
        else:
            self._loop.call_soon_threadsafe(self._put, msg)

    def _put(self, msg: dict) -> None:
        self.history.append(msg)
        for q in list(self._subs):
            q.put_nowait(msg)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)


class BusLogHandler(logging.Handler):
    def __init__(self, bus: Bus) -> None:
        super().__init__(level=logging.DEBUG)
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        self.bus.publish("log", {"level": record.levelname, "logger": record.name, "line": record.getMessage()})


# -- state ---------------------------------------------------------------------------

def _slim(event: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in event.items() if k not in ("result_text",)}


class UIState:
    def __init__(self, *, gateway: ModelGateway | None = None, settings: Settings | None = None,
                 records_target: str | None = None, bank_api: BankApiSettings | None = None,
                 use_guard_llm: bool = True, results_dirs: dict[str, Path] | None = None,
                 eval_runner: Callable | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.settings = self.settings.with_model(self.settings.guard_model).with_model(self.settings.model)
        self._gateway = gateway
        self.records_target = records_target
        self.bank_api = bank_api
        self.use_guard_llm = use_guard_llm
        self.results_dirs = results_dirs or EVALS
        self.bus = Bus()
        self.records: RecordsClient | None = None
        self.session: ChatSession | None = None
        self.busy = False
        self.eval_runs: dict[str, dict[str, Any]] = {}
        self.packs: dict[str, dict[str, Any]] = {}
        self._eval_runner = eval_runner or self._run_eval_subprocess
        self._handler = BusLogHandler(self.bus)

    @property
    def gateway(self) -> ModelGateway:
        if self._gateway is None:
            from kyc_workflow.gateway import AnthropicBackend

            self._gateway = HeliosGateway(AnthropicBackend(), self.settings)
        return self._gateway

    async def start(self) -> None:
        self.bus.bind(asyncio.get_running_loop())
        for name in ("kyc_workflow.chat", "kyc_workflow.ui"):
            logging.getLogger(name).addHandler(self._handler)
            if logging.getLogger(name).level > logging.INFO or logging.getLogger(name).level == 0:
                logging.getLogger(name).setLevel(logging.INFO)
        self.records = RecordsClient(self.records_target, self.bank_api)
        await self.records.__aenter__()
        log.info("ui connected to MCP server %s (%d tools)", self.records.target, len(self.records.tools))
        self.new_session()

    async def stop(self) -> None:
        if self.records is not None:
            await self.records.__aexit__(None, None, None)
        for name in ("kyc_workflow.chat", "kyc_workflow.ui"):
            logging.getLogger(name).removeHandler(self._handler)

    def new_session(self) -> ChatSession:
        assert self.records is not None
        classifier = None
        if self.use_guard_llm:
            classifier = make_intent_classifier(self.gateway, self.settings, self.settings.guard_model, "UI", "CHAT-GUARD")
        guard = Guardrails(allowed_tools=self.records.names, intent_classifier=classifier)
        self.session = ChatSession(self.gateway, self.records, self.settings, analyst_id="UI", guardrails=guard,
                                   on_event=lambda e: self.bus.publish("event", _slim(e)))
        self.bus.publish("usage", {"session_id": self.session.session_id, "turn": None, "totals": self.session.totals})
        return self.session

    def status(self) -> dict[str, Any]:
        s = self.session
        return {
            "model": self.settings.model, "guard_model": self.settings.guard_model if self.use_guard_llm else None,
            "eval_model": self.settings.eval_model, "mcp": self.records.target if self.records else None,
            "tools": sorted(self.records.names) if self.records else [],
            "session_id": s.session_id if s else None, "turns": s.turn if s else 0,
            "totals": s.totals if s else None, "last_turn": s.last_turn if s else None,
            "audit_log": str(s.log_path) if s else None, "busy": self.busy, "examples": EXAMPLE_QUESTIONS,
            "evals": {name: {k: v for k, v in run.items() if k != "task"} for name, run in self.eval_runs.items()},
            "packs": {rid: self._pack_summary(p) for rid, p in self.packs.items()},
            "demo_reviews": DEMO_REVIEWS,
        }

    # -- workflow -----------------------------------------------------------------------

    @staticmethod
    def _pack_summary(entry: dict[str, Any]) -> dict[str, Any]:
        pack = entry.get("pack")
        return {"status": entry["status"], "started": entry["started"], "finished": entry.get("finished"), "error": entry.get("error"),
                "use_model": entry["use_model"], "steps": entry["steps"],
                "exceptions": sum(1 for f in pack.findings if f.kind == "exception") if pack else None,
                "model_calls": len(pack.model_calls) if pack else None,
                "input_tokens": sum(m.input_tokens for m in pack.model_calls) if pack else None,
                "output_tokens": sum(m.output_tokens for m in pack.model_calls) if pack else None}

    async def start_pack(self, review_id: str, use_model: bool = True) -> dict[str, Any]:
        entry = self.packs.get(review_id)
        if entry and entry["status"] == "running":
            return self._pack_summary(entry)
        entry = {"status": "running", "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "use_model": use_model,
                 "steps": {}, "pack": None, "check": None, "error": None}
        self.packs[review_id] = entry
        entry["task"] = asyncio.create_task(self._run_pack(review_id, entry))
        return self._pack_summary(entry)

    async def _run_pack(self, review_id: str, entry: dict[str, Any]) -> None:
        def progress(e: dict[str, Any]) -> None:
            kind, step = e["event"], e.get("step")
            if step:
                st = entry["steps"].setdefault(step, {"status": "pending"})
                if kind == "step_start":
                    st.update(status="running", model_step=e.get("model_step", False))
                elif kind == "step_end":
                    st.update(status="done", duration_ms=e.get("duration_ms"), findings=e.get("findings"), exceptions=e.get("exceptions"))
                elif kind == "step_skipped":
                    st.update(status="skipped")
                elif kind == "step_error":
                    st.update(status="error", error=e.get("message"))
                elif kind == "model_call":
                    st.setdefault("model_calls", []).append({k: e.get(k) for k in ("purpose", "request_id", "input_tokens", "output_tokens", "latency_ms", "stop_reason")})
            self.bus.publish("pack", {"review_id": review_id, **_slim(e)})

        try:
            pack = await build_pack(review_id, self.records, self.gateway if entry["use_model"] else None, settings=self.settings,
                                    use_model=entry["use_model"], analyst_id="UI", on_progress=progress)
            entry.update(status="done", pack=pack, markdown=pack_markdown(pack))
        except LoadError as err:
            entry.update(status="error", error=str(err))
        except Exception as err:  # noqa: BLE001
            log.exception("pack failed")
            entry.update(status="error", error=f"{type(err).__name__}: {err}")
        entry["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.bus.publish("pack", {"review_id": review_id, "event": "pack_status", "status": entry["status"], "error": entry["error"]})

    def pack_payload(self, review_id: str) -> dict[str, Any] | None:
        entry = self.packs.get(review_id)
        if not entry:
            return None
        out = self._pack_summary(entry) | {"review_id": review_id}
        if entry.get("pack"):
            out["pack"] = entry["pack"].model_dump(mode="json")
            out["markdown"] = entry.get("markdown")
        if entry.get("check"):
            out["check"] = entry["check"].model_dump(mode="json")
            out["check_markdown"] = check_markdown(entry["check"])
        return out

    async def run_check(self, review_id: str, outcome: str | None, clauses: list[str] | None, rationale: str | None,
                        use_model: bool = True) -> dict[str, Any]:
        entry = self.packs.get(review_id)
        if not entry or not entry.get("pack"):
            raise KeyError(review_id)
        report = await build_check(entry["pack"], self.gateway if use_model else None, settings=self.settings,
                                   recorded_outcome=outcome, clauses=clauses, rationale=rationale, analyst_id="UI", use_model=use_model,
                                   on_progress=lambda e: self.bus.publish("pack", {"review_id": review_id, **_slim(e)}))
        entry["check"] = report
        return {"check": report.model_dump(mode="json"), "check_markdown": check_markdown(report)}

    async def document_text(self, stored_filename: str) -> str | None:
        assert self.records is not None
        result = await self.records.call("get_document", {"stored_filename": stored_filename})
        if result.is_error:
            return None
        try:
            return json.loads(result.text).get("text")
        except ValueError:
            return None

    async def ask(self, text: str) -> dict[str, Any]:
        assert self.session is not None
        if self.busy:
            raise RuntimeError("a turn is already running")
        self.busy = True
        try:
            reply = await self.session.ask(text)
        finally:
            self.busy = False
        self.bus.publish("usage", {"session_id": self.session.session_id, "turn": self.session.last_turn,
                                   "totals": self.session.totals})
        return {"reply": reply, "turn": self.session.last_turn}

    # -- evals -------------------------------------------------------------------------

    async def run_eval(self, name: str) -> dict[str, Any]:
        if name not in self.results_dirs:
            raise KeyError(name)
        run = self.eval_runs.get(name)
        if run and run["status"] == "running":
            return run
        run = {"name": name, "status": "running", "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "exit_code": None, "summary": None}
        self.eval_runs[name] = run
        run["task"] = asyncio.create_task(self._eval_runner(name, run))
        self.bus.publish("eval", {"name": name, "status": "running"})
        return {k: v for k, v in run.items() if k != "task"}

    async def _run_eval_subprocess(self, name: str, run: dict[str, Any]) -> None:
        extra = ["--limit", "6"] if name == "pack" else []
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", f"evals.{name}.run", *extra, cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        last = ""
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if not line or line.startswith("["):  # skip the SDK's INFO lines
                continue
            last = line if ("cases" in line or "accuracy" in line) else last
            self.bus.publish("eval", {"name": name, "line": line})
        code = await proc.wait()
        run.update(status="passed" if code == 0 else "failed", exit_code=code, summary=last,
                   finished=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.bus.publish("eval", {"name": name, "status": run["status"], "exit_code": code, "summary": last})

    def eval_history(self) -> dict[str, list[dict[str, Any]]]:
        return {name: read_results(name, path) for name, path in self.results_dirs.items()}


def read_results(name: str, root: Path) -> list[dict[str, Any]]:
    """Past runs of one eval, oldest first, from whatever is on disk."""
    runs: list[dict[str, Any]] = []
    if not root.exists():
        return runs
    if name == "routing":
        for f in sorted(root.glob("*.json")):
            try:
                d = json.loads(f.read_text())
            except ValueError:
                continue
            runs.append({"at": _stamp(f.name), "model": d.get("model"), "score": d.get("mean"),
                         "passed": d.get("exact"), "total": len(d.get("cases", [])), "file": f.name})
    else:
        for f in sorted(root.glob("*/report.json")):
            try:
                d = json.loads(f.read_text())
            except ValueError:
                continue
            runs.append({"at": _stamp(f.parent.name), "model": d.get("model"), "score": d.get("pass_rate"),
                         "passed": d.get("passed"), "total": d.get("total"), "judge": d.get("judge") if isinstance(d.get("judge"), dict) else None,
                         "file": f.parent.name, "detail": {k: d.get(k) for k in ("overturn_recall", "false_alarm_rate", "citation_rate", "faithfulness_mean") if k in d}})
    return runs


def _stamp(name: str) -> str:
    m = re.match(r"(\d{8}T\d{6}Z)", name)
    if not m:
        return name
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat(timespec="seconds")


# -- app -----------------------------------------------------------------------------

def create_app(state: UIState) -> Starlette:
    @asynccontextmanager
    async def lifespan(app: Starlette):
        await state.start()
        try:
            yield
        finally:
            await state.stop()

    async def index(_: Request):
        return FileResponse(STATIC / "index.html")

    async def status(_: Request):
        return JSONResponse(state.status())

    async def chat_new(_: Request):
        if state.busy:
            return JSONResponse({"error": "a turn is running"}, status_code=409)
        s = state.new_session()
        return JSONResponse({"session_id": s.session_id, "audit_log": str(s.log_path)})

    async def chat_ask(request: Request):
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "empty message"}, status_code=400)
        if state.busy:
            return JSONResponse({"error": "a turn is already running"}, status_code=409)
        return JSONResponse(await state.ask(text))

    async def chat_history(_: Request):
        s = state.session
        msgs = [e for e in (s.events if s else []) if e["event"] in ("user_message", "assistant_message")]
        return JSONResponse({"messages": [{"role": "user" if e["event"] == "user_message" else "assistant",
                                           "turn": e["turn"], "text": e.get("text", ""),
                                           "withheld": e.get("withheld", False), "refused": e.get("refused", False)}
                                          for e in msgs]})

    async def workflow_pack(request: Request):
        body = await request.json()
        review_id = (body.get("review_id") or body.get("case_id") or "").strip()
        if not review_id:
            return JSONResponse({"error": "review_id required"}, status_code=400)
        return JSONResponse(await state.start_pack(review_id, bool(body.get("use_model", True))))

    async def workflow_pack_get(request: Request):
        payload = state.pack_payload(request.path_params["review_id"])
        if payload is None:
            return JSONResponse({"error": "no pack for that review in this session"}, status_code=404)
        return JSONResponse(payload)

    async def workflow_check(request: Request):
        body = await request.json()
        try:
            return JSONResponse(await state.run_check(body.get("review_id", ""), body.get("recorded_outcome"),
                                                      body.get("clauses"), body.get("rationale"), bool(body.get("use_model", True))))
        except KeyError:
            return JSONResponse({"error": "build the pack first"}, status_code=404)

    async def workflow_reviews(_: Request):
        return JSONResponse({"reviews": DEMO_REVIEWS, "built": list(state.packs)})

    async def document(request: Request):
        text = await state.document_text(request.path_params["name"])
        if text is None:
            return JSONResponse({"error": "document not found"}, status_code=404)
        return JSONResponse({"stored_filename": request.path_params["name"], "text": text})

    async def evals_run(request: Request):
        body = await request.json()
        try:
            return JSONResponse(await state.run_eval(body.get("name", "")))
        except KeyError:
            return JSONResponse({"error": f"unknown eval {body.get('name')!r}"}, status_code=400)

    async def evals_history(_: Request):
        return JSONResponse(state.eval_history())

    async def events(request: Request):
        q = state.bus.subscribe()

        async def stream():
            try:
                for msg in list(state.bus.history):
                    yield f"data: {json.dumps(msg, default=str)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(msg, default=str)}\n\n"
            finally:
                state.bus.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return Starlette(
        routes=[
            Route("/", index),
            Route("/api/status", status),
            Route("/api/chat/new", chat_new, methods=["POST"]),
            Route("/api/chat/ask", chat_ask, methods=["POST"]),
            Route("/api/chat/history", chat_history),
            Route("/api/workflow/pack", workflow_pack, methods=["POST"]),
            Route("/api/workflow/pack/{review_id}", workflow_pack_get),
            Route("/api/workflow/check", workflow_check, methods=["POST"]),
            Route("/api/workflow/reviews", workflow_reviews),
            Route("/api/document/{name}", document),
            Route("/api/evals/run", evals_run, methods=["POST"]),
            Route("/api/evals/history", evals_history),
            Route("/api/events", events),
            Mount("/static", StaticFiles(directory=str(STATIC)), name="static"),
        ],
        lifespan=lifespan,
    )
