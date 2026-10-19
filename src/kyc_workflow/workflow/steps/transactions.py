"""Transaction cross-checks: arithmetic the policy states as numbers. No model.

§4.7(b) turnover against declared, §7.2(a) monthly swings, §7.2(b) and
§4.7(c) counterparties outside declared markets, §7.4(a) Group 3
jurisdictions, §7.4(b) cash intensity against the Appendix B band, §7.4(c)
pass-through. §7.4(d) structuring is reported as not assessed: the policy
names no threshold.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from kyc_workflow.workflow.models import CaseFile, Citation, Finding, MonthlyFlow, TransactionProfile
from kyc_workflow.workflow.policy import Policy

CASH_MARKERS = ("cash", "atm")


def _amount(rec) -> float:
    try:
        return float(rec.data.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_cash(counterparty: str) -> bool:
    c = (counterparty or "").lower()
    return any(m in c for m in CASH_MARKERS)


def _business_days_after(d: date, n: int) -> date:
    out = d
    added = 0
    while added < n:
        out += timedelta(days=1)
        if out.weekday() < 5:
            added += 1
    return out


def analyse(case: CaseFile, policy: Policy) -> tuple[TransactionProfile, list[Finding]]:
    rules = policy.rules
    cust = case.customer
    findings: list[Finding] = []
    txns = case.transactions
    credits = [t for t in txns if t.get("direction") == "credit"]
    debits = [t for t in txns if t.get("direction") == "debit"]
    credits_total = sum(_amount(t) for t in credits)
    debits_total = sum(_amount(t) for t in debits)

    months: dict[str, MonthlyFlow] = {}
    cur = case.period_start.replace(day=1)
    while cur <= case.period_end:
        months[cur.strftime("%Y-%m")] = MonthlyFlow(month=cur.strftime("%Y-%m"), credits=0.0, debits=0.0, credit_count=0, debit_count=0)
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    for t in txns:
        key = (t.get("date") or "")[:7]
        if key in months:
            m = months[key]
            if t.get("direction") == "credit":
                m.credits += _amount(t); m.credit_count += 1
            else:
                m.debits += _amount(t); m.debit_count += 1

    declared = None
    try:
        declared = float(cust.get("expected_annual_turnover_sgd")) if cust.get("expected_annual_turnover_sgd") else None
    except ValueError:
        declared = None
    ratio = (credits_total / declared) if declared else None

    cash_credits = sum(_amount(t) for t in credits if _is_cash(t.get("counterparty")))
    cash_share = (cash_credits / credits_total) if credits_total else None

    countries: dict[str, float] = defaultdict(float)
    for t in credits + debits:
        countries[(t.get("counterparty_country") or "").upper() or "??"] += _amount(t)
    declared_markets = [m.strip().upper() for m in (cust.get("declared_markets") or "").split("|") if m.strip()]
    outside = {c: v for c, v in countries.items() if declared_markets and c not in declared_markets and c != "??"}
    group3 = {c: v for c, v in countries.items() if policy.group_of(c)[0] == 3}

    cp: dict[str, float] = defaultdict(float)
    for t in credits:
        cp[t.get("counterparty") or "?"] += _amount(t)
    top = sorted(cp.items(), key=lambda kv: -kv[1])[:8]

    # pass-through: a material credit substantially matched by debits within five business days
    pt_events, pt_value = 0, 0.0
    active_months = max(1, sum(1 for m in months.values() if m.credits > 0))
    pt_floor = max(rules.material_credit, rules.pass_through_min_share * credits_total / active_months)
    deb_by_date = sorted(((date.fromisoformat(t.get("date")[:10]), _amount(t)) for t in debits if t.get("date")), key=lambda x: x[0])
    for t in credits:
        amt = _amount(t)
        if amt < pt_floor or not t.get("date"):
            continue
        d0 = date.fromisoformat(t.get("date")[:10])
        d1 = _business_days_after(d0, rules.pass_through_business_days)
        out = sum(a for d, a in deb_by_date if d0 <= d <= d1)
        if out >= rules.pass_through_match * amt:
            pt_events += 1
            pt_value += amt

    largest = sorted(credits, key=_amount, reverse=True)[:5]
    profile = TransactionProfile(
        accounts=[a.get("account_number") for a in case.accounts], period_start=case.period_start, period_end=case.period_end,
        credits_total=round(credits_total, 2), debits_total=round(debits_total, 2), credit_count=len(credits), debit_count=len(debits),
        months=list(months.values()), declared_turnover=declared, turnover_ratio=round(ratio, 3) if ratio is not None else None,
        cash_credits=round(cash_credits, 2), cash_share=round(cash_share, 4) if cash_share is not None else None,
        countries=dict(sorted(countries.items(), key=lambda kv: -kv[1])), declared_markets=declared_markets,
        outside_markets=outside, group3=group3, top_counterparties=[(k, round(v, 2)) for k, v in top],
        pass_through_events=pt_events, pass_through_value=round(pt_value, 2),
        largest_credits=[{"date": t.get("date"), "amount": _amount(t), "counterparty": t.get("counterparty"),
                          "country": t.get("counterparty_country"), "account": t.get("account")} for t in largest],
    )

    txn_cite = [Citation(system="transaction-summary", dataset="transactions_*", record_id=", ".join(profile.accounts),
                         field=f"{case.period_start} to {case.period_end}", request_id=txns[0].citation.request_id if txns else None)]
    decl_cite = Citation(system="customer-master", dataset="customers", record_id=case.customer_ref,
                         field="expected_annual_turnover_sgd", request_id=cust.citation.request_id)

    if not txns:
        findings.append(Finding(clause="4.1", kind="not_assessed", severity="medium", step="transactions",
                                title="No transactions on record for the review period",
                                detail=f"No credits or debits were found on {len(case.accounts)} account(s) between {case.period_start} and {case.period_end}. "
                                       "Transactions on record start in December 2024; the twelve-month summary §4.1 requires cannot be built from the export.",
                                citations=txn_cite))
        return profile, findings

    # §4.7(b) / §5.4 counterpart
    if declared is None:
        findings.append(Finding(clause="4.7(b)", kind="not_assessed", severity="medium", step="transactions",
                                title="Declared turnover not on the record", detail="expected_annual_turnover_sgd is empty, so the 200% cross-check cannot be run.",
                                citations=[decl_cite]))
    else:
        pct = round(ratio * 100)
        if ratio > rules.turnover_tolerance:
            findings.append(Finding(clause="4.7(b)", kind="exception", severity="medium", step="transactions",
                                    title=f"Credits are {pct}% of declared turnover, above the 200% tolerance",
                                    detail=f"Aggregate credits S${credits_total:,.0f} over {case.period_start} to {case.period_end} against declared expected annual turnover S${declared:,.0f}. "
                                           "An exception on this cross-check that the file does not itself resolve engages §4.5(d).",
                                    values={"credits_total": credits_total, "declared": declared, "ratio": ratio}, citations=txn_cite + [decl_cite]))
        else:
            findings.append(Finding(clause="4.7(b)", kind="condition_met", severity="info", step="transactions",
                                    title=f"Credits are {pct}% of declared turnover, within the 200% tolerance",
                                    detail=f"Aggregate credits S${credits_total:,.0f} against declared S${declared:,.0f}.",
                                    values={"credits_total": credits_total, "declared": declared, "ratio": ratio}, citations=txn_cite + [decl_cite]))

    # §7.2(a) monthly swings sustained
    series = [m.credits for m in profile.months]
    run, worst = 0, 0
    swings: list[str] = []
    for i in range(3, len(series)):
        trailing = sum(series[i - 3:i]) / 3
        if trailing <= 0:
            run = 0
            continue
        swing = (series[i] - trailing) / trailing
        if abs(swing) > rules.monthly_swing:
            run += 1
            swings.append(f"{profile.months[i].month} {swing:+.0%}")
            worst = max(worst, run)
        else:
            run = 0
    if worst >= rules.swing_months:
        findings.append(Finding(clause="7.2(a)", kind="exception", severity="medium", step="transactions",
                                title=f"Monthly credits moved beyond ±40% of the trailing average for {worst} consecutive months",
                                detail="Indicator of Material Change under §7.2(a): " + ", ".join(swings[-worst:]) +
                                       ". Whether this is consistent with expected behaviour is assessed under §7.3.",
                                values={"swings": swings}, citations=txn_cite))
    else:
        findings.append(Finding(clause="7.2(a)", kind="condition_met", severity="info", step="transactions",
                                title="No sustained monthly swing beyond ±40%", detail="Monthly credit values stayed within ±40% of the trailing three-month average, or did so for fewer than three consecutive months.",
                                citations=txn_cite))

    # §7.2(b) / §4.7(c) outside declared markets
    if not declared_markets:
        findings.append(Finding(clause="4.7(c)", kind="not_assessed", severity="low", step="transactions",
                                title="Declared markets not on the record", detail="declared_markets is empty, so counterparty jurisdictions cannot be compared with it.",
                                citations=[Citation(system="customer-master", dataset="customers", record_id=case.customer_ref, field="declared_markets", request_id=cust.citation.request_id)]))
    elif outside:
        desc = ", ".join(f"{policy.group_of(c)[1]} S${v:,.0f}" for c, v in sorted(outside.items(), key=lambda kv: -kv[1]))
        findings.append(Finding(clause="7.2(b)", kind="exception", severity="medium", step="transactions",
                                title="Activity with counterparties outside the declared markets",
                                detail=f"Declared markets {', '.join(policy.group_of(m)[1] for m in declared_markets)}; observed outside them: {desc}. Indicator of Material Change (§7.2(b)) and a §4.7(c) comparison point.",
                                values={"outside": outside}, citations=txn_cite))
    else:
        findings.append(Finding(clause="4.7(c)", kind="condition_met", severity="info", step="transactions",
                                title="All counterparty jurisdictions are within the declared markets", detail=f"Declared {', '.join(declared_markets)}; observed {', '.join(k for k in countries if k != '??')}.",
                                citations=txn_cite))

    # §7.4(a) Group 3
    if group3:
        findings.append(Finding(clause="7.4(a)", kind="exception", severity="high", step="transactions",
                                title="Counterparty in a Group 3 jurisdiction",
                                detail="High-risk indicator: " + ", ".join(f"{policy.group_of(c)[1]} S${v:,.0f}" for c, v in group3.items()) +
                                       ". With a Material Change in the same review this engages §4.4(c).",
                                values={"group3": group3}, citations=txn_cite))

    # §7.4(b) cash intensity
    baseline = policy.baseline_for(cust.get("ssic_code"))
    if cash_share is not None and baseline:
        lo, hi = baseline.cash_band
        if cash_share > hi:
            findings.append(Finding(clause="7.4(b)", kind="exception", severity="high", step="transactions",
                                    title=f"Cash is {cash_share:.0%} of credits, above the {lo:.0%}-{hi:.0%} band for {baseline.industry}",
                                    detail=f"Cash credits S${cash_credits:,.0f} of S${credits_total:,.0f}. Appendix B band for SSIC {baseline.ssic}. High-risk indicator under §7.4(b).",
                                    values={"cash_share": cash_share, "band": [lo, hi]}, citations=txn_cite))
        else:
            findings.append(Finding(clause="7.4(b)", kind="condition_met", severity="info", step="transactions",
                                    title=f"Cash is {cash_share:.0%} of credits, within the {lo:.0%}-{hi:.0%} band for {baseline.industry}",
                                    detail=f"Appendix B band for SSIC {baseline.ssic}.", citations=txn_cite))
    elif cash_share:
        findings.append(Finding(clause="7.4(b)", kind="information", severity="low", step="transactions",
                                title=f"Cash is {cash_share:.0%} of credits; no Appendix B band applies",
                                detail="No SSIC code on the record (individual customer or code missing), so the cash-intensity band cannot be looked up.",
                                values={"cash_share": cash_share}, citations=txn_cite))

    # §7.4(c) pass-through
    if pt_events:
        findings.append(Finding(clause="7.4(c)", kind="exception", severity="high", step="transactions",
                                title=f"{pt_events} credit(s) substantially left the account within five business days",
                                detail=f"S${pt_value:,.0f} of credits of at least S${pt_floor:,.0f} (half the average monthly credits) were matched by debits of at least {rules.pass_through_match:.0%} within {rules.pass_through_business_days} business days. High-risk indicator under §7.4(c).",
                                values={"events": pt_events, "value": pt_value}, citations=txn_cite))

    # §7.4(d) structuring: no threshold in the policy
    findings.append(Finding(clause="7.4(d)", kind="not_assessed", severity="low", step="transactions",
                            title="Structuring pattern not assessed", detail="POL-042 names no reporting or monitoring threshold for §7.4(d); to be settled with Compliance before this indicator is computed.",
                            citations=txn_cite))

    return profile, findings
