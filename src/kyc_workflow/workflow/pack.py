"""build_pack: the fixed sequence that produces an evidence pack for one review.

    load_case -> transactions -> screening -> history -> documents (model)
    -> consistency (model) -> ownership -> matching (model) -> plausibility (model)
    -> narratives (model) -> reviewer (model) -> clauses -> render

Code decides the path and does the arithmetic; the model reads and
compares inside the steps marked (model). Every model call goes through the
gateway with the review id as case id, and every step is written to an
audit log in audit/pack/. A model step that fails leaves a not_assessed
finding and the pack continues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from kyc_workflow.chat.mcp_client import RecordsClient
from kyc_workflow.config import Settings
from kyc_workflow.gateway import GatewayError, ModelGateway, ModelRequest
from kyc_workflow.workflow.loader import CaseLoader
from kyc_workflow.workflow.models import CaseFile, Citation, EvidencePack, Finding, ModelCallNote
from kyc_workflow.workflow.policy import Policy, load_policy
from kyc_workflow.workflow.steps import clauses as clauses_step
from kyc_workflow.workflow.steps import history as history_step
from kyc_workflow.workflow.steps import model_steps
from kyc_workflow.workflow.steps import screening as screening_step
from kyc_workflow.workflow.steps import transactions as transactions_step
from kyc_workflow.workflow.steps.documents import read_documents

log = logging.getLogger("kyc_workflow.pack")

STEPS = ["load_case", "transactions", "screening", "history", "documents", "consistency", "ownership",
         "matching", "plausibility", "narratives", "reviewer", "clauses", "render"]
MODEL_STEPS = {"documents", "consistency", "matching", "plausibility", "narratives", "reviewer"}


class PackRun:
    """One build: audit log, progress callback, model-call accounting."""

    def __init__(self, review_id: str, gateway: ModelGateway | None, settings: Settings, model: str | None,
                 analyst_id: str, audit_dir: Path | None, on_progress: Callable[[dict[str, Any]], None] | None) -> None:
        self.review_id = review_id
        self.gateway = gateway
        self.settings = settings
        self.model = model or settings.model
        self.analyst_id = analyst_id
        self.on_progress = on_progress
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.log_path = (audit_dir or settings.audit_dir / "pack") / f"{review_id.replace('/', '_')}_{stamp}.jsonl"
        self.model_calls: list[ModelCallNote] = []
        self.step_errors: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []

    def event(self, kind: str, **payload: Any) -> None:
        e = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "review_id": self.review_id, "event": kind, **payload}
        self.events.append(e)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(e, default=str) + "\n")
        level = logging.WARNING if kind in ("step_error", "model_error") else logging.INFO
        summary = {k: v for k, v in payload.items() if k not in ("findings",)}
        log.log(level, "%s %s %s", self.review_id, kind, json.dumps(summary, default=str)[:400])
        if self.on_progress:
            self.on_progress(e)

    effort: str | None = "medium"  # reading and comparing, not open-ended reasoning

    def ask(self, step: str, purpose: str, system: str, user: str, schema: type[BaseModel],
            max_tokens: int = 4096) -> tuple[BaseModel, str]:
        """One structured model call through the gateway, logged. Raises GatewayError."""
        if self.gateway is None:
            raise GatewayError("no gateway: model steps are disabled for this run")
        request = ModelRequest(case_id=self.review_id, analyst_id=self.analyst_id, system=system, user=user,
                               output_schema=schema, model=self.model, max_tokens=max_tokens, effort=self.effort)
        started = time.monotonic()
        try:
            response = self.gateway.complete(request)
        except GatewayError as err:
            self.event("model_error", step=step, purpose=purpose, error_type=type(err).__name__, message=str(err))
            raise
        note = ModelCallNote(step=step, purpose=purpose, request_id=response.request_id, model=response.model,
                             input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                             latency_ms=round(response.latency_ms, 1))
        self.model_calls.append(note)
        self.event("model_call", step=step, purpose=purpose, request_id=response.request_id, model=response.model,
                   input_tokens=note.input_tokens, output_tokens=note.output_tokens, latency_ms=note.latency_ms,
                   stop_reason=response.stop_reason, latency_total_ms=round((time.monotonic() - started) * 1000, 1))
        if response.parsed is None:
            self.event("model_error", step=step, purpose=purpose, error_type="StructuredOutputMissing",
                       message=f"stop_reason={response.stop_reason}; the answer was probably cut off at max_tokens")
            raise GatewayError(f"structured output missing (stop_reason={response.stop_reason})")
        return response.parsed, response.request_id


async def build_pack(review_id: str, records: RecordsClient, gateway: ModelGateway | None, *, settings: Settings | None = None,
                     policy: Policy | None = None, model: str | None = None, analyst_id: str = "WORKFLOW",
                     use_model: bool = True, audit_dir: Path | None = None,
                     on_progress: Callable[[dict[str, Any]], None] | None = None) -> EvidencePack:
    settings = settings or Settings.from_env()
    policy = policy or load_policy(rules=None)
    run = PackRun(review_id, gateway if use_model else None, settings, model, analyst_id, audit_dir, on_progress)
    run.event("pack_start", model=run.model if use_model and gateway else None, steps=STEPS,
              rules={"document_validity_days": policy.rules.document_validity_days, "document_rule_all_tiers": policy.rules.document_rule_all_tiers,
                     "payslip_is_independent": policy.rules.payslip_is_independent, "turnover_tolerance": policy.rules.turnover_tolerance})
    findings: list[Finding] = []
    not_assessed: list[str] = []

    def step(name: str):
        run.event("step_start", step=name, model_step=name in MODEL_STEPS)
        return time.monotonic()

    def done(name: str, started: float, new: list[Finding], **extra: Any) -> None:
        findings.extend(new)
        run.event("step_end", step=name, findings=len(new), exceptions=sum(1 for f in new if f.kind == "exception"),
                  duration_ms=round((time.monotonic() - started) * 1000, 1), **extra)

    def failed(name: str, started: float, err: Exception, clause: str = "4.1") -> None:
        run.step_errors[name] = f"{type(err).__name__}: {err}"
        run.event("step_error", step=name, error_type=type(err).__name__, message=str(err)[:300],
                  duration_ms=round((time.monotonic() - started) * 1000, 1))
        not_assessed.append(f"{name}: {type(err).__name__}")
        findings.append(Finding(clause=clause, kind="not_assessed", severity="medium", step=name,
                                title=f"Step '{name}' did not complete", detail=f"{type(err).__name__}: {str(err)[:200]}. The analyst performs this check by hand.",
                                citations=[Citation(system="workflow", dataset="step", record_id=name)]))

    # -- load ------------------------------------------------------------------------------
    t = step("load_case")
    case: CaseFile = await CaseLoader(records, policy).load(review_id)
    run.event("step_end", step="load_case", duration_ms=round((time.monotonic() - t) * 1000, 1), customer_ref=case.customer_ref,
              tier=case.tier, in_scope=case.in_scope, period=[str(case.period_start), str(case.period_end)], period_inferred=case.period_inferred,
              accounts=len(case.accounts), owners=len(case.beneficial_owners), hits=len(case.screening_hits), cases=len(case.cases),
              documents=len(case.documents), transactions=len(case.transactions), request_ids=len(case.request_ids))

    # -- deterministic ----------------------------------------------------------------------
    t = step("transactions")
    profile, new = transactions_step.analyse(case, policy)
    done("transactions", t, new, credits=profile.credits_total, ratio=profile.turnover_ratio)

    t = step("screening")
    items, new = screening_step.assess(case, policy)
    done("screening", t, new, hits=len(items), unresolved=sum(1 for i in items if i.status == "unresolved"))

    t = step("history")
    done("history", t, history_step.assess(case, policy))

    # -- model ------------------------------------------------------------------------------
    CLAUSE_OF = {"documents": "4.1", "consistency": "4.7(d)", "ownership": "6.5", "matching": "5.4", "plausibility": "5.4", "narratives": "8.7"}
    reads = []
    model_on = gateway is not None and use_model

    def skip(name: str) -> None:
        run.event("step_skipped", step=name, reason="model steps disabled")
        not_assessed.append(f"{name}: model steps disabled")
        findings.append(Finding(clause="4.1", kind="not_assessed", severity="low", step=name,
                                title=f"Step '{name}' not run (model disabled)", detail="Run with the model enabled to read documents and compare them with the record.",
                                citations=[Citation(system="workflow", dataset="step", record_id=name)]))

    # documents first: every later model step reads what the model read
    t = step("documents")
    if not model_on:
        skip("documents")
    else:
        try:
            reads, new = await asyncio.to_thread(read_documents, case, policy, run.ask)
            done("documents", t, new, documents=len(reads))
        except Exception as err:
            failed("documents", t, err, CLAUSE_OF["documents"])

    # the comparisons are independent of each other: run them at the same time
    code_findings_so_far = list(findings)

    async def run_step(name: str, fn):
        t = step(name)
        if name in MODEL_STEPS and not model_on:
            skip(name)
            return name, t, None, None
        try:
            return name, t, await asyncio.to_thread(fn), None
        except Exception as err:
            return name, t, None, err

    results = await asyncio.gather(
        run_step("consistency", lambda: model_steps.consistency(case, reads, policy, run.ask)),
        run_step("ownership", lambda: model_steps.ownership(case, reads, policy)),
        run_step("matching", lambda: model_steps.matching(case, profile, reads, policy, run.ask)),
        run_step("plausibility", lambda: model_steps.plausibility(case, profile, reads, code_findings_so_far, policy, run.ask)),
        run_step("narratives", lambda: model_steps.narratives(case, items, policy, run.ask)),
    )
    for name, t, result, err in results:
        if err is not None:
            failed(name, t, err, CLAUSE_OF[name])
        elif result is not None:
            done(name, t, result)

    # ids before the reviewer sees the list
    for i, f in enumerate(findings, 1):
        f.id = f"F-{i:02d}"

    t = step("reviewer")
    if gateway is None or not use_model:
        run.event("step_skipped", step="reviewer", reason="model steps disabled")
    else:
        try:
            new = await asyncio.to_thread(model_steps.reviewer, case, findings, profile, items, reads, policy, run.ask)
            for j, f in enumerate(new, len(findings) + 1):
                f.id = f"F-{j:02d}"
            done("reviewer", t, new)
        except Exception as err:
            failed("reviewer", t, err)

    t = step("clauses")
    conds = clauses_step.conditions(findings)
    run.event("step_end", step="clauses", duration_ms=round((time.monotonic() - t) * 1000, 1),
              exceptions=sum(1 for c in conds if c.status == "exception"), met=sum(1 for c in conds if c.status == "met"))

    pack = EvidencePack(
        review_id=review_id, customer_ref=case.customer_ref, customer_name=case.customer_name, customer_type=case.customer.get("customer_type"),
        tier=case.tier, in_scope=case.in_scope, scope_note=case.scope_note, period_start=case.period_start, period_end=case.period_end,
        period_inferred=case.period_inferred, built_at=datetime.now(timezone.utc), model=run.model if use_model and gateway else None,
        transactions=profile, screening=items, documents=reads, findings=findings, conditions=conds, model_calls=run.model_calls,
        not_assessed=not_assessed, request_ids=case.request_ids, audit_log=str(run.log_path),
        recorded_outcome=case.recorded_note.get("outcome_code") if case.recorded_note else None,
        recorded_clauses=[c.strip() for c in (case.recorded_note.get("clauses_cited") if case.recorded_note else "").replace("|", ",").split(",") if c.strip()],
        recorded_rationale=case.recorded_note.get("rationale_text") if case.recorded_note else None,
        recorded_analyst=case.recorded_note.get("analyst_id") if case.recorded_note else None,
    )
    run.event("pack_end", findings=len(findings), exceptions=sum(1 for f in findings if f.kind == "exception"),
              model_suggested=sum(1 for f in findings if f.kind == "model_suggested"), model_calls=len(run.model_calls),
              input_tokens=sum(m.input_tokens for m in run.model_calls), output_tokens=sum(m.output_tokens for m in run.model_calls))
    return pack


async def build_check(pack: EvidencePack, gateway: ModelGateway | None, *, settings: Settings | None = None,
                      recorded_outcome: str | None = None, clauses: list[str] | None = None, rationale: str | None = None,
                      model: str | None = None, analyst_id: str = "WORKFLOW", use_model: bool = True,
                      audit_dir: Path | None = None, on_progress: Callable[[dict[str, Any]], None] | None = None):
    """The pre-submit check of a recorded outcome against a pack. Defaults to the write-up on the pack."""
    from kyc_workflow.workflow.check import check

    settings = settings or Settings.from_env()
    run = PackRun(pack.review_id, gateway if use_model else None, settings, model, analyst_id,
                  audit_dir or settings.audit_dir / "check", on_progress)
    outcome = recorded_outcome if recorded_outcome is not None else pack.recorded_outcome
    cited = clauses if clauses is not None else pack.recorded_clauses
    text = rationale if rationale is not None else pack.recorded_rationale
    run.event("check_start", outcome=outcome, clauses=cited, rationale_chars=len(text or ""), model=run.model if use_model and gateway else None)
    ask = run.ask if (gateway is not None and use_model) else None
    try:
        report = await asyncio.to_thread(check, pack, outcome, cited, text, ask)
    except GatewayError as err:
        run.event("step_error", step="check", error_type=type(err).__name__, message=str(err)[:200])
        report = await asyncio.to_thread(check, pack, outcome, cited, text, None)
    report.model_calls = list(run.model_calls)
    run.event("check_end", flags=[f.code for f in report.flags], clean=report.clean, faithfulness=report.rationale_faithfulness,
              model_calls=len(run.model_calls))
    return report
