"""Clause conditions: what the findings say about each policy condition.

This is a lookup table over findings, not a decision. For every condition
in §4.3, every trigger in §4.4 and §4.5 and every cross-check in §4.7 it
records met, not met, exception, information or not assessed, with the
findings that support it. The outcome under §4.2 is the analyst's.
"""

from __future__ import annotations

from kyc_workflow.workflow.models import ClauseCondition, Finding

CONDITIONS: list[tuple[str, str, tuple[str, ...]]] = [
    ("4.3(a)", "No unresolved screening result and no Relevant Screening Hit", ("8.3", "8.5", "4.3(a)", "4.4(a)", "4.4(b)")),
    ("4.3(b)", "No Material Change, or change assessed as expected behaviour (§7.3)", ("7.2", "7.3")),
    ("4.3(c)", "Profile attributes consistent with activity and documents (§4.7(c), (d))", ("4.7(c)", "4.7(d)", "7.5", "5.4")),
    ("4.3(d)", "Every mandatory cross-check at §4.7 completed without exception", ("4.7",)),
    ("4.4(a)", "Sanctions True Match", ("4.4(a)",)),
    ("4.4(b)", "Relevant Screening Hit on the customer or a beneficial owner", ("4.4(b)", "8.5")),
    ("4.4(c)", "Material Change together with a high-risk indicator (§7.4)", ("7.4",)),
    ("4.4(d)", "Second lapsed RFI or stated refusal", ("4.4(d)",)),
    ("4.4(e)", "Record-to-document discrepancy not attributable to error", ("4.4(e)",)),
    ("4.5(a)", "Profile attribute stale or inconsistent with activity (§7.5)", ("7.5", "4.5(a)")),
    ("4.5(b)", "Material Change not consistent with expected behaviour, no §7.4 indicator", ("4.5(b)",)),
    ("4.5(c)", "Document inconsistent with the record, attributable to error or age", ("4.5(c)",)),
    ("4.5(d)", "Cross-check exception the file does not resolve", ("4.7(b)", "4.5(d)")),
    ("4.7(a)", "Screening reviewed for the customer and each beneficial owner", ("4.7(a)", "6.5(b)", "8.3")),
    ("4.7(b)", "Turnover within 200% of declared", ("4.7(b)",)),
    ("4.7(c)", "Activity and markets against counterparties and products", ("4.7(c)", "7.2(b)")),
    ("4.7(d)", "Document substance consistent with the record", ("4.7(d)",)),
    ("4.8.3", "No RFI outstanding", ("4.8.3",)),
    ("6.5", "Beneficial owners refreshed, screened and dispositioned", ("6.5", "6.6")),
    ("5.4", "Activity plausible against declared employment and source of funds", ("5.4",)),
    ("7.4", "High-risk indicators", ("7.4",)),
]


def material_change_with_indicator(findings: list[Finding]) -> list[Finding]:
    """§4.4(c): a Material Change (§7.2 exception, or §6.6) together with a §7.4 indicator in the same review."""
    change = [f for f in findings if f.kind == "exception" and (f.clause.startswith("7.2") or f.clause.startswith("6.6"))]
    indicator = [f for f in findings if f.kind == "exception" and f.clause.startswith("7.4")]
    return change + indicator if change and indicator else []


def conditions(findings: list[Finding]) -> list[ClauseCondition]:
    out: list[ClauseCondition] = []
    for clause, label, prefixes in CONDITIONS:
        related = [f for f in findings if any(f.clause.startswith(p) for p in prefixes)]
        if clause == "4.4(c)":
            both = material_change_with_indicator(findings)
            out.append(ClauseCondition(clause=clause, label=label, status="exception" if both else ("information" if related else "not_assessed"),
                                       finding_ids=[f.id for f in (both or related)]))
            continue
        ids = [f.id for f in related]
        kinds = {f.kind for f in related}
        if not related:
            status = "not_assessed"
        elif "exception" in kinds:
            status = "exception"
        elif kinds <= {"not_assessed"}:
            status = "not_assessed"
        elif "condition_met" in kinds and "model_suggested" not in kinds:
            status = "met"
        else:
            status = "information"
        out.append(ClauseCondition(clause=clause, label=label, status=status, finding_ids=ids))
    return out
