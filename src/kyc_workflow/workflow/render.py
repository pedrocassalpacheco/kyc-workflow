"""Markdown rendering of an evidence pack and a check report. The structured
objects are the record; this is a view of them for a reader."""

from __future__ import annotations

from kyc_workflow.workflow.models import CheckReport, EvidencePack, Finding

KIND_LABEL = {"exception": "EXCEPTION", "condition_met": "met", "information": "info", "not_assessed": "NOT ASSESSED", "model_suggested": "model-suggested"}
STATUS_LABEL = {"met": "met", "not_met": "not met", "exception": "EXCEPTION", "not_assessed": "not assessed", "information": "see findings"}


def _cite(f: Finding) -> str:
    return "; ".join(c.label() + (f" [{c.request_id[:8]}]" if c.request_id else "") for c in f.citations) or "no citation"


def _finding(f: Finding) -> str:
    who = "Claude read" if f.origin == "model" else "code"
    head = f"- **{f.id} §{f.clause}** [{KIND_LABEL[f.kind]}, {f.severity}, {who}] {f.title}"
    return head + f"\n  {f.detail}\n  _Sources: {_cite(f)}_"


def pack_markdown(pack: EvidencePack) -> str:
    out = [f"# Evidence pack: {pack.review_id}", ""]
    out.append(f"**Customer** {pack.customer_name} ({pack.customer_ref}, {pack.customer_type})  ")
    out.append(f"**Review period** {pack.period_start} to {pack.period_end}" + (" (inferred)" if pack.period_inferred else "") + f"  ")
    out.append(f"**Risk tier** {pack.tier}  **Built** {pack.built_at:%Y-%m-%d %H:%M} UTC  **Model** {pack.model or 'none (code only)'}")
    if pack.scope_note:
        out += ["", f"> {pack.scope_note}"]
    out += ["", "This pack states what the records show against POL-042 conditions. It does not rate, decide or recommend an outcome; a named analyst does.", ""]

    ex = [f for f in pack.findings if f.kind == "exception"]
    out += [f"## Exceptions ({len(ex)})", ""]
    out += [_finding(f) for f in sorted(ex, key=lambda f: ({"high": 0, "medium": 1, "low": 2, "info": 3}[f.severity], f.clause))] or ["- none"]

    out += ["", "## Clause conditions", "", "| Clause | Condition | Status | Findings |", "|---|---|---|---|"]
    for c in pack.conditions:
        out.append(f"| §{c.clause} | {c.label} | {STATUS_LABEL[c.status]} | {', '.join(c.finding_ids) or '-'} |")

    if pack.transactions:
        t = pack.transactions
        out += ["", "## Transactions", "",
                f"Accounts {', '.join(t.accounts)}; credits S${t.credits_total:,.0f} in {t.credit_count} items; debits S${t.debits_total:,.0f} in {t.debit_count} items; "
                f"declared turnover {('S$%s' % format(t.declared_turnover, ',.0f')) if t.declared_turnover else 'not recorded'}"
                + (f"; ratio {t.turnover_ratio:.0%}" if t.turnover_ratio is not None else "") + (f"; cash {t.cash_share:.0%}" if t.cash_share is not None else "") + ".",
                "", "| Month | Credits | # | Debits | # |", "|---|---|---|---|---|"]
        out += [f"| {m.month} | {m.credits:,.0f} | {m.credit_count} | {m.debits:,.0f} | {m.debit_count} |" for m in t.months]
        if t.top_counterparties:
            out += ["", "Top credit counterparties: " + "; ".join(f"{n} S${v:,.0f}" for n, v in t.top_counterparties[:5])]

    if pack.screening:
        out += ["", "## Screening", "", "| Hit | Subject | Category | Score | Band | Status | Reason | Issues |", "|---|---|---|---|---|---|---|---|"]
        out += [f"| {i.hit_id} | {i.subject} ({i.role}) | {i.category}{(' cat ' + i.media_category) if i.media_category else ''} | {i.score} | {i.band} | {i.status} | {i.reason_code or '-'} | {'; '.join(i.issues) or '-'} |"
                for i in pack.screening]

    if pack.documents:
        out += ["", "## Documents (read by Claude)", "", "| Document | Type | Issuer | Dated | Age (days) | Independent | Subject |", "|---|---|---|---|---|---|---|"]
        out += [f"| {d.stored_filename} | {d.doc_type} | {d.issuer or '?'} | {d.document_date or '?'} | {d.age_days if d.age_days is not None else '?'} | {d.independent if d.independent is not None else '?'} | {d.subject or '?'} |"
                for d in pack.documents]

    rest = [f for f in pack.findings if f.kind in ("condition_met", "information")]
    out += ["", f"## Other findings ({len(rest)})", ""] + ([_finding(f) for f in rest] or ["- none"])
    ms = [f for f in pack.findings if f.kind == "model_suggested"]
    out += ["", f"## Model-suggested, not verified ({len(ms)})", "",
            "A second read of the file by Claude. These are candidates for the analyst to check, not findings of the fixed checks.", ""] + ([_finding(f) for f in ms] or ["- none"])
    na = [f for f in pack.findings if f.kind == "not_assessed"]
    out += ["", f"## Not assessed ({len(na)})", ""] + ([_finding(f) for f in na] or ["- none"])

    out += ["", "## Model calls", "", "| Step | Purpose | Request | Model | In | Out | ms |", "|---|---|---|---|---|---|---|"]
    out += [f"| {m.step} | {m.purpose} | {m.request_id[:8]} | {m.model} | {m.input_tokens} | {m.output_tokens} | {m.latency_ms:.0f} |" for m in pack.model_calls] or ["| - | none | | | | | |"]
    out += ["", f"Bank API requests: {len(pack.request_ids)}. Audit log: `{pack.audit_log}`.", ""]
    return "\n".join(out)


def check_markdown(report: CheckReport) -> str:
    out = [f"# Check report: {report.review_id}", "",
           f"**Recorded outcome** {report.recorded_outcome}  **Clauses cited** {', '.join(report.clauses_cited) or 'none'}  "
           f"**Rationale** {report.rationale_chars} chars  **Result** {'CLEAN' if report.clean else f'{len(report.flags)} flag(s)'}", ""]
    out += ["## Flags", ""] + ([f"- **{f.code}** (§{f.clause}, {f.severity}) {f.detail}" + (f" _[{', '.join(f.finding_ids)}]_" if f.finding_ids else "") for f in report.flags] or ["- none"])
    if report.rationale_faithfulness is not None:
        out += ["", f"## Rationale against the pack", "", f"Faithfulness {report.rationale_faithfulness:.2f}."]
        out += [f"- Unsupported: {s}" for s in report.unsupported_statements] or ["- every statement in the rationale is supported by the pack"]
    return "\n".join(out) + "\n"
