"""Screening assessment: dispositions, bands and elimination rules. Code only;
the adverse-media category (§8.7) is filled in by the model step when hits need it.

§8.2 bands, §8.3 every result dispositioned (none recorded = unresolved),
§8.4 elimination only in the weak or possible band with recorded identifier
mismatches and never for sanctions at analyst level, §8.5 relevant hits,
§6.5(b) every beneficial owner screened, §4.7(a) results reviewed per owner.
"""

from __future__ import annotations

from kyc_workflow.workflow.models import CaseFile, Citation, Finding, ScreeningItem
from kyc_workflow.workflow.policy import Policy

STATUS = {"": "unresolved", "FALSE": "eliminated", "TRUE": "true_match"}


def assess(case: CaseFile, policy: Policy) -> tuple[list[ScreeningItem], list[Finding]]:
    items: list[ScreeningItem] = []
    findings: list[Finding] = []
    for rec in case.screening_hits:
        try:
            score = float(rec.get("score")) if rec.get("score") else None
        except ValueError:
            score = None
        band = policy.band(score)
        status = STATUS.get(rec.get("disposition_status").upper(), "unresolved")
        item = ScreeningItem(hit_id=rec.get("hit_id"), subject=rec.get("screened_subject_name"), role=rec.get("screened_subject_role"),
                             category=rec.get("category"), score=score, band=band, status=status,
                             reason_code=rec.get("disposition_reason_code"), remark=rec.get("disposition_remark"),
                             headline=rec.get("media_headline"))
        cite = Citation(system="screening", dataset="screening_hits", record_id=item.hit_id, request_id=rec.citation.request_id)
        who = f"{item.subject} ({item.role})"
        if status == "unresolved":
            item.issues.append("no disposition recorded")
            findings.append(Finding(clause="8.3", kind="exception", severity="high" if band == "strong" else "medium", step="screening",
                                    title=f"{item.category} hit {item.hit_id} on {who} has no disposition ({band} band, score {score})",
                                    detail="A result with no recorded disposition is treated as Possible Match — Unresolved, and §4.3(a) cannot be satisfied while it stands. "
                                           + (f"Headline: {item.headline}" if item.headline else ""),
                                    values={"band": band, "score": score, "category": item.category}, citations=[cite]))
        elif status == "eliminated":
            problems = []
            if band == "strong":
                problems.append("a strong-band result shall not be Eliminated at analyst level (§8.4)")
            if item.category == "sanctions":
                problems.append("sanctions results are dispositioned by the Group Sanctions Desk, not at analyst level (§8.4)")
            if not item.reason_code:
                problems.append("no differentiating identifier recorded (§8.4 requires each identifier relied on, §8.8 the evidence)")
            if problems:
                item.issues.extend(problems)
                findings.append(Finding(clause="8.4", kind="exception", severity="high", step="screening",
                                        title=f"Elimination of {item.category} hit {item.hit_id} on {who} does not meet §8.4",
                                        detail="; ".join(problems) + f". Score {score} ({band} band), reason code {item.reason_code or 'none'}.",
                                        values={"band": band, "score": score, "reason": item.reason_code}, citations=[cite]))
            else:
                findings.append(Finding(clause="8.4", kind="condition_met", severity="info", step="screening",
                                        title=f"{item.category} hit {item.hit_id} on {who} eliminated under §8.4 ({band} band, {item.reason_code})",
                                        detail=item.remark or "Identifier mismatch recorded.", citations=[cite]))
        else:  # true match
            if item.category == "sanctions":
                findings.append(Finding(clause="4.4(a)", kind="exception", severity="high", step="screening",
                                        title=f"Sanctions True Match on {who} ({item.hit_id})", detail="A sanctions True Match is escalated immediately under §4.4(a) and §8.6.1.",
                                        citations=[cite]))
            elif item.category == "pep":
                findings.append(Finding(clause="4.4(b)", kind="exception", severity="high", step="screening",
                                        title=f"PEP True Match on {who} ({item.hit_id})", detail="A PEP True Match not previously approved is escalated under §4.4(b) and §8.6.2.",
                                        citations=[cite]))
            else:
                findings.append(Finding(clause="8.5(c)", kind="exception", severity="high", step="screening",
                                        title=f"Adverse media True Match on {who} ({item.hit_id})", detail=f"Relevant if the subject matter is Category 1, or Category 2 and recent and credible (§8.7). Headline: {item.headline}",
                                        citations=[cite]))
        items.append(item)

    # §6.5(b): every beneficial owner screened
    screened_ids = {r.get("screened_subject_id") for r in case.screening_hits}
    for bo in case.beneficial_owners:
        if bo.get("bo_id") not in screened_ids:
            findings.append(Finding(clause="6.5(b)", kind="information", severity="medium", step="screening",
                                    title=f"No screening result on file for beneficial owner {bo.get('bo_name')} ({bo.get('bo_id')}, {bo.get('effective_pct')}%)",
                                    detail="§6.5(b) requires current screening for each Beneficial Owner. The export holds results only where a hit occurred, so this may mean a clean screen or no screen; the analyst confirms which.",
                                    citations=[Citation(system="customer-master", dataset="beneficial_owners", record_id=bo.get("bo_id"), request_id=bo.citation.request_id)]))

    if not case.screening_hits:
        findings.append(Finding(clause="4.3(a)", kind="information", severity="info", step="screening",
                                title="No screening hits on file for the customer or connected parties",
                                detail="No results in screening_hits for this customer; the export holds results only where a name matched.",
                                citations=[Citation(system="screening", dataset="screening_hits", record_id=case.customer_ref)]))
    elif all(i.status != "unresolved" for i in items):
        findings.append(Finding(clause="4.3(a)", kind="condition_met", severity="info", step="screening",
                                title="Every screening result carries a disposition", detail=f"{len(items)} result(s), none unresolved.",
                                citations=[Citation(system="screening", dataset="screening_hits", record_id=case.customer_ref)]))
    return items, findings
