"""Prior case history: open RFIs, lapsed RFIs, previous review outcomes. Code only;
the model step reads the narratives for refusals and unanswered requests (§4.4(d))."""

from __future__ import annotations

from datetime import date, timedelta

from kyc_workflow.workflow.models import CaseFile, Citation, Finding
from kyc_workflow.workflow.policy import Policy


def assess(case: CaseFile, policy: Policy) -> list[Finding]:
    findings: list[Finding] = []
    rfis = [c for c in case.cases if c.get("outcome") == "rfi_issued" or c.get("case_type") == "rfi"]
    today = case.period_end
    for c in rfis:
        cite = Citation(system="case-history", dataset="case_history", record_id=c.get("case_id"), request_id=c.citation.request_id)
        closed = c.get("closed_dt")
        opened = c.get("opened_dt")
        if not closed:
            findings.append(Finding(clause="4.8.3", kind="exception", severity="high", step="history",
                                    title=f"RFI case {c.get('case_id')} opened {opened} is still open",
                                    detail="A review is completed under §4.3 or §4.4 only on receipt of the RFI response; the rating under review remains in effect while an RFI is outstanding. "
                                           f"Narrative: {c.get('narrative')[:300]}",
                                    citations=[cite]))
        else:
            try:
                days = (date.fromisoformat(closed[:10]) - date.fromisoformat(opened[:10])).days
            except ValueError:
                days = None
            findings.append(Finding(clause="4.8", kind="information", severity="info", step="history",
                                    title=f"RFI case {c.get('case_id')} ({opened} to {closed}" + (f", {days} days)" if days is not None else ")"),
                                    detail=f"Outcome {c.get('outcome')}. Narrative: {c.get('narrative')[:300]}",
                                    citations=[cite]))
    if len(rfis) >= 2:
        findings.append(Finding(clause="4.4(d)", kind="information", severity="medium", step="history",
                                title=f"{len(rfis)} RFI cases on this customer",
                                detail="§4.4(d) applies to a second consecutive RFI that lapsed unanswered, or a stated refusal; the narratives are read for either.",
                                citations=[Citation(system="case-history", dataset="case_history", record_id=c.get("case_id"), request_id=c.citation.request_id) for c in rfis]))

    for n in case.prior_notes:
        findings.append(Finding(clause="4.9", kind="information", severity="info", step="history",
                                title=f"Previous review {n.get('review_id')} on {n.get('review_date')}: outcome {n.get('outcome_code')}, clauses {n.get('clauses_cited') or 'none cited'}",
                                detail=n.get("rationale_text")[:400], citations=[n.citation]))
    alerts = [c for c in case.cases if c.get("case_type") == "transaction_alert"]
    for c in alerts:
        findings.append(Finding(clause="7.1", kind="information", severity="low", step="history",
                                title=f"Prior transaction alert {c.get('case_id')} ({c.get('alert_type')}), outcome {c.get('outcome')}",
                                detail=c.get("narrative")[:300],
                                citations=[Citation(system="case-history", dataset="case_history", record_id=c.get("case_id"), request_id=c.citation.request_id)]))
    if not case.cases:
        findings.append(Finding(clause="4.1", kind="information", severity="info", step="history",
                                title="No prior cases on this customer", detail="case_history holds no rows for the customer.",
                                citations=[Citation(system="case-history", dataset="case_history", record_id=case.customer_ref)]))
    return findings
