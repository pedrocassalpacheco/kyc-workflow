"""The evaluation set for the evidence pack and the check: the QA sample.

`qa_sample.csv` is the QA function's re-performance log: 75 reviews, 60
where QA concurred with the analyst and 15 it overturned, each with the
reason. The workflow never reads this file (it is not served by the MCP
server); the eval reads it from disk as ground truth.

Each overturn reason maps to what a good pack must surface:

  profile inconsistency not resolved -> an RFI trigger stands in the file
  unresolved screening or discrepancy -> an escalation trigger stands
  information on file resolved it     -> no RFI trigger stands (analyst over-asked)
  no escalation trigger               -> no escalation trigger stands
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from kyc_workflow.config import PROJECT_ROOT

QA_PATH = PROJECT_ROOT / "data" / "qa_sample.csv"

RFI_SIGNALS = ("4.5(a)", "4.5(b)", "4.5(c)", "4.5(d)", "4.7(b)", "7.5", "5.4", "4.4(e)")
ESCALATION_SIGNALS = ("4.4(a)", "4.4(b)", "4.4(c)", "4.4(d)", "4.4(e)", "8.5(c)", "8.3", "8.4")


@dataclass
class QACase:
    review_id: str
    recorded_outcome: str
    qa_outcome: str
    concurs: bool
    reason: str

    @property
    def kind(self) -> str:
        if self.concurs:
            return "concur"
        r = self.reason.lower()
        if "not resolved" in r and "required information" in r:
            return "needed_rfi"
        if "unresolved screening" in r or "record discrepancy" in r:
            return "needed_escalation"
        if "resolved the matter" in r:
            return "over_asked"
        if "no escalation trigger" in r:
            return "over_escalated"
        return "other"


def load_cases(path: Path = QA_PATH) -> list[QACase]:
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    return [QACase(review_id=r["review_id"], recorded_outcome=r["recorded_outcome"], qa_outcome=r["qa_outcome"],
                   concurs=r["qa_concurs"] == "Y", reason=r["reason_for_difference"]) for r in rows]


def overturn_surfaced(case: QACase, exception_clauses: set[str], check_flags: set[str]) -> bool | None:
    """Did the pack and check surface what QA found? None when the case kind is not scored."""
    has = lambda sigs: any(c.startswith(s) for c in exception_clauses for s in sigs)
    if case.kind == "needed_rfi":
        return has(RFI_SIGNALS) or "RFI_TRIGGER_IGNORED" in check_flags or "ESCALATION_TRIGGER_IGNORED" in check_flags
    if case.kind == "needed_escalation":
        return has(ESCALATION_SIGNALS) or "ESCALATION_TRIGGER_IGNORED" in check_flags or "CONFIRMED_OVER_UNRESOLVED_HIT" in check_flags
    if case.kind == "over_asked":
        return "RFI_WITHOUT_TRIGGER" in check_flags
    if case.kind == "over_escalated":
        return "ESCALATION_WITHOUT_TRIGGER" in check_flags
    return None
