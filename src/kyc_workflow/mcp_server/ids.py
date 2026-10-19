"""Identifier conventions in the bank's export.

The export was pulled from several source systems and Data Ops does not
normalise on the way out, so one customer appears as `CIF-1234567`,
`CIF1234567`, `CIF123456` or a bare `1234567` depending on the file. The
API's filters are exact-match, so a lookup tries each shape in turn and
reports which one the file used.
"""

from __future__ import annotations

import re


def customer_ref_variants(ref: str) -> list[str]:
    """Shapes of a customer reference to try, most likely first."""
    ref = ref.strip()
    digits = re.sub(r"\D", "", ref)
    candidates = [ref]
    if digits:
        candidates += [f"CIF-{digits}", f"CIF{digits}", digits]
    return _dedupe(candidates)


def account_number_variants(account: str) -> list[str]:
    """Account numbers are stored with and without leading zeros."""
    account = account.strip()
    candidates = [account]
    stripped = account.lstrip("0")
    if stripped and stripped != account:
        candidates.append(stripped)
    if account.isdigit() and len(account) < 10:
        candidates.append(account.zfill(10))
    return _dedupe(candidates)


def review_id_variants(review_id: str) -> list[str]:
    """Review ids come as VGB-PR-2026-0041, PR2026-0041, vgb_pr_26_0041 or 0041."""
    rid = review_id.strip()
    m = re.search(r"(?:(\d{2})?(\d{2}))?[-_]?(\d{4})$", re.sub(r"^(vgb[-_]?pr[-_]?|pr)", "", rid, flags=re.I))
    candidates = [rid]
    if m:
        yy, seq = m.group(2), m.group(3)
        year = f"20{yy}" if yy else "2026"
        candidates += [f"VGB-PR-{year}-{seq}", f"PR{year}-{seq}", f"vgb_pr_{year[2:]}_{seq}", seq]
    return _dedupe(candidates)


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen
