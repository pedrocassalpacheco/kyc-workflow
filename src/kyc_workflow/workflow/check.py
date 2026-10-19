"""The pre-submit check: an analyst's recorded outcome against the evidence pack.

Code compares the recorded outcome and the clauses cited with the pack's
conditions (no clause named, outcome confirmed over an unresolved hit or an
open RFI, escalation triggers ignored, an RFI or escalation with no trigger
in the file, a cited clause the pack contradicts, stale or customer-supplied
evidence relied on, ownership change without a registry extract). The
model, when available, reads the rationale text and marks each factual
statement as supported by the pack or not. Nothing here decides the file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from kyc_workflow.workflow.models import CheckFlag, CheckReport, EvidencePack, ModelCallNote
from kyc_workflow.workflow.steps.clauses import material_change_with_indicator

OUTCOMES = {"unchanged": "rating confirmed (§4.3)", "request_info": "RFI (§4.5)", "escalate": "escalation (§4.4)"}

ESCALATION = ("4.4(a)", "4.4(b)", "4.4(c)", "4.4(d)", "4.4(e)", "8.5(c)")
RFI = ("4.5(a)", "4.5(b)", "4.5(c)", "4.5(d)", "4.7(b)", "7.5", "7.2(a)", "7.2(b)", "5.4")
UNRESOLVED = ("8.3", "8.4", "4.3(a)")


class Statement(BaseModel):
    text: str = Field(description="one factual statement from the rationale, as written")
    supported: bool = Field(description="true if the pack's findings or figures support it")
    basis: str = Field(description="the finding id or figure that supports it, or why nothing does")


class RationaleCheck(BaseModel):
    statements: list[Statement] = Field(description="Every factual statement in the rationale, at most twelve")


def _exceptions(pack: EvidencePack, prefixes: tuple[str, ...]) -> list:
    return [f for f in pack.findings if f.kind == "exception" and any(f.clause.startswith(p) for p in prefixes)]


def check(pack: EvidencePack, recorded_outcome: str | None, clauses_cited: list[str], rationale: str | None,
          ask=None) -> CheckReport:
    outcome = (recorded_outcome or "").strip()
    cited = [c.strip() for c in clauses_cited if c.strip()]
    flags: list[CheckFlag] = []
    calls: list[ModelCallNote] = []

    def flag(code: str, clause: str, severity: Literal["high", "medium", "low", "info"], detail: str, findings=()) -> None:
        flags.append(CheckFlag(code=code, clause=clause, severity=severity, detail=detail, finding_ids=[f.id for f in findings]))

    if not outcome:
        flag("NO_OUTCOME", "4.2", "high", "No outcome recorded; every review concludes with exactly one of three outcomes.")
    elif outcome not in OUTCOMES:
        flag("UNKNOWN_OUTCOME", "4.2", "medium", f"Outcome {outcome!r} is not one of {list(OUTCOMES)}.")
    if not cited:
        flag("NO_CLAUSE", "4.9", "high", "No POL-042 clause cited. The rationale must cite the clauses applied so an independent reviewer can reconstruct the decision.")
    if rationale is not None and len(rationale.strip()) < 40:
        flag("THIN_RATIONALE", "4.9", "medium", "The rationale is too short to reconstruct the decision from the file.")

    unresolved = _exceptions(pack, UNRESOLVED)
    escal = _exceptions(pack, ESCALATION) + material_change_with_indicator(pack.findings)
    rfi = _exceptions(pack, RFI)
    open_rfi = _exceptions(pack, ("4.8.3",))
    ownership = _exceptions(pack, ("6.6", "6.5"))

    if outcome == "unchanged":
        if unresolved:
            flag("CONFIRMED_OVER_UNRESOLVED_HIT", "4.3(a)", "high", f"Rating confirmed while {len(unresolved)} screening result(s) are undispositioned or eliminated outside §8.4.", unresolved)
        if open_rfi:
            flag("CONFIRMED_WITH_OPEN_RFI", "4.8.3", "high", "Rating confirmed while an RFI is outstanding; the review is completed only on receipt of the response.", open_rfi)
        if escal:
            flag("ESCALATION_TRIGGER_IGNORED", "4.4", "high", f"Rating confirmed while {len(escal)} escalation trigger(s) stand in the file; escalation takes precedence (§4.6).", escal)
        elif rfi:
            flag("RFI_TRIGGER_IGNORED", "4.5", "medium", f"Rating confirmed while {len(rfi)} RFI trigger(s) stand in the file that the file does not itself resolve.", rfi)
    elif outcome == "request_info":
        if escal:
            flag("ESCALATION_TRIGGER_IGNORED", "4.4", "high", f"RFI recorded while {len(escal)} escalation trigger(s) stand; escalation takes precedence over an RFI (§4.6).", escal)
        if not rfi and not unresolved and not escal:
            flag("RFI_WITHOUT_TRIGGER", "4.5", "medium", "RFI recorded but the pack shows no cross-check exception, profile mismatch or document inconsistency that the file leaves unresolved.")
    elif outcome == "escalate":
        if not escal:
            flag("ESCALATION_WITHOUT_TRIGGER", "4.4", "medium", "Escalation recorded but the pack shows no §4.4 trigger: no sanctions or relevant hit, no change with a high-risk indicator, no refusal, no substantive discrepancy.")

    # cited clauses against what the pack holds on them
    for c in cited:
        base = c.split("(")[0]
        exact = [f for f in pack.findings if f.clause == c]
        related = exact or [f for f in pack.findings if f.clause.startswith(base)]
        exceptions_on = [f for f in related if f.kind == "exception"]
        if c.startswith("4.3") and (unresolved or escal or rfi or open_rfi):
            flag("CLAUSE_CONTRADICTED", c, "high", f"§{c} cited to confirm, but the pack records exceptions against the §4.3 conditions.", unresolved + escal + rfi + open_rfi)
        elif exact and all(f.kind == "not_assessed" for f in exact):
            flag("CLAUSE_NOT_ASSESSED", c, "low", f"§{c} cited, but the pack could not assess it: {exact[0].title}. The rationale must carry that check itself.", exact)
        elif outcome == "unchanged" and exceptions_on:
            flag("CLAUSE_CONTRADICTED", c, "medium", f"§{c} cited to confirm while the pack records an exception on it.", exceptions_on)
        elif outcome in ("request_info", "escalate") and c.startswith(("4.4", "4.5", "7.", "8.", "6.6")) and related and not exceptions_on:
            flag("TRIGGER_NOT_IN_PACK", c, "low", f"§{c} cited as the trigger, but the pack records no exception on it; the rationale should say what evidence engages it.", related)
        elif not related:
            flag("CLAUSE_NOT_EVIDENCED", c, "low", f"§{c} cited but nothing in the pack bears on it; the rationale should say what was looked at.")

    # evidence quality
    stale = [f for f in pack.findings if f.step == "documents" and f.kind == "exception"]
    if stale:
        flag("STALE_EVIDENCE", "5.4", "low" if pack.tier != 4 else "high",
             f"{len(stale)} document(s) older than the {stale[0].values.get('window_days')}-day window (rule applied to all tiers by default; the policy states it for CRR 4).", stale)
    not_independent = [d for d in pack.documents if d.independent is False and d.doc_type in ("payslip extract", "source of funds letter", "remittance cover note")]
    independent = [d for d in pack.documents if d.independent is True]
    if not_independent and not independent:
        flag("CUSTOMER_SUPPLIED_ONLY", "5.4", "medium", "Source-of-funds evidence on file is customer-supplied only: " + ", ".join(d.stored_filename for d in not_independent) + ".")
    if ownership and not any(c.startswith("6.") for c in cited):
        flag("OWNERSHIP_CHANGE_UNADDRESSED", "6.6", "medium", "The registry extract disagrees with the owners or officers on record and no Part 6 clause is cited.", ownership)
    unverified = [f for f in pack.findings if f.kind == "model_suggested"]
    if unverified:
        flag("MODEL_SUGGESTIONS_TO_CHECK", "4.1", "info", f"{len(unverified)} model-suggested point(s) await the analyst's check.", unverified)

    faith = None
    unsupported: list[str] = []
    if ask is not None and rationale and rationale.strip():
        facts = "\n".join(f"- [{f.id}] §{f.clause} {f.kind}: {f.title}" for f in pack.findings)
        tx = pack.transactions
        figures = (f"credits S${tx.credits_total:,.0f} ({tx.credit_count}); debits S${tx.debits_total:,.0f}; declared {tx.declared_turnover}; ratio {tx.turnover_ratio}; "
                   f"cash share {tx.cash_share}; period {tx.period_start} to {tx.period_end}") if tx else "(no transaction profile)"
        docs = "\n".join(f"- {d.stored_filename}: {d.doc_type}, issuer {d.issuer}, dated {d.document_date}, facts {d.key_facts[:3]}" for d in pack.documents) or "(none)"
        system = ("You check an analyst's closing rationale against the evidence pack built from the same file. Split the rationale into its factual "
                  "statements and mark each as supported by the pack or not, naming the finding or figure. Judge support strictly: a figure that differs, "
                  "a document the pack does not hold, or a fact the pack does not record is unsupported. Do not judge the outcome.")
        user = f"EVIDENCE PACK FINDINGS\n{facts}\n\nFIGURES\n{figures}\n\nDOCUMENTS READ\n{docs}\n\nRATIONALE\n{rationale}"
        parsed, rid = ask("check", "rationale against the pack", system, user, RationaleCheck)
        total = len(parsed.statements)
        if total:
            faith = sum(1 for s in parsed.statements if s.supported) / total
            unsupported = [f"{s.text} ({s.basis})" for s in parsed.statements if not s.supported]
            if unsupported:
                flag("RATIONALE_UNSUPPORTED", "4.9", "medium" if faith < 0.8 else "low",
                     f"{len(unsupported)} of {total} statements in the rationale are not supported by the pack.")

    clean = not any(f.severity in ("high", "medium") for f in flags)
    return CheckReport(review_id=pack.review_id, recorded_outcome=outcome, clauses_cited=cited,
                       rationale_chars=len(rationale or ""), flags=flags, rationale_faithfulness=faith,
                       unsupported_statements=unsupported, clean=clean, built_at=datetime.now(timezone.utc), model_calls=calls)
