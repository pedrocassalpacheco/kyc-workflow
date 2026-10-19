"""Shapes of the evidence pack.

Everything the pack says is a `Finding`: one statement about one policy
condition, with the values it rests on and citations back to the records.
Findings are conditions, never outcomes: "§4.7(b) exception: credits are
360% of declared turnover" is a finding; "this should be an RFI" is not,
and nothing here can express it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Origin = Literal["code", "model"]
Kind = Literal["exception", "condition_met", "information", "not_assessed", "model_suggested"]
Severity = Literal["high", "medium", "low", "info"]


class Citation(BaseModel):
    """Where a statement came from: enough to open the record again."""

    system: str
    dataset: str
    record_id: str | None = None
    field: str | None = None
    document: str | None = None
    request_id: str | None = None
    excerpt: str | None = None

    def label(self) -> str:
        parts = [self.system, self.dataset]
        if self.document:
            parts.append(self.document)
        elif self.record_id:
            parts.append(self.record_id)
        if self.field:
            parts.append(self.field)
        return " / ".join(parts)


class Record(BaseModel):
    """A raw row from a record system with its citation."""

    data: dict[str, Any]
    citation: Citation

    def get(self, key: str, default: str = "") -> str:
        v = self.data.get(key)
        return default if v is None else str(v)


class DocumentRecord(BaseModel):
    stored_filename: str
    original_filename: str
    doc_type: str
    review_id: str | None = None
    customer_id: str | None = None
    belongs_to_this_review: bool
    text: str
    citation: Citation


class CaseFile(BaseModel):
    """Everything the five sources hold for one review, as loaded."""

    review_id: str
    matched_review_id: str | None
    review: Record | None
    customer_ref: str
    period_start: date
    period_end: date
    period_inferred: bool
    tier: int | None
    in_scope: bool
    scope_note: str
    customer: Record
    accounts: list[Record]
    beneficial_owners: list[Record]
    officers: list[Record]
    screening_hits: list[Record]
    cases: list[Record]
    prior_reviews: list[Record]
    prior_notes: list[Record]
    recorded_note: Record | None = Field(default=None, description="The analyst's write-up of this review, if completed.")
    documents: list[DocumentRecord]
    transactions: list[Record]
    request_ids: list[str]
    loaded_at: datetime

    @property
    def customer_name(self) -> str:
        return self.customer.get("legal_name") or self.customer.get("full_name_and_address") or self.customer_ref

    @property
    def is_entity(self) -> bool:
        return self.customer.get("customer_type") == "entity"


class Finding(BaseModel):
    id: str = ""
    clause: str
    kind: Kind
    severity: Severity
    title: str
    detail: str
    values: dict[str, Any] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    origin: Origin = "code"
    step: str = ""
    model_request_id: str | None = None
    verified: bool = Field(default=True, description="False for model-suggested items until an analyst checks them.")


class MonthlyFlow(BaseModel):
    month: str
    credits: float
    debits: float
    credit_count: int
    debit_count: int


class TransactionProfile(BaseModel):
    accounts: list[str]
    period_start: date
    period_end: date
    credits_total: float
    debits_total: float
    credit_count: int
    debit_count: int
    months: list[MonthlyFlow]
    declared_turnover: float | None
    turnover_ratio: float | None
    cash_credits: float
    cash_share: float | None
    countries: dict[str, float]
    declared_markets: list[str]
    outside_markets: dict[str, float]
    group3: dict[str, float]
    top_counterparties: list[tuple[str, float]]
    pass_through_events: int
    pass_through_value: float
    largest_credits: list[dict[str, Any]]


class ScreeningItem(BaseModel):
    hit_id: str
    subject: str
    role: str
    category: str
    score: float | None
    band: str
    status: str  # true_match | unresolved | eliminated
    reason_code: str
    remark: str
    headline: str
    media_category: str | None = None  # 1, 2, 3 from the model, when assessed
    issues: list[str] = Field(default_factory=list)


class DocumentRead(BaseModel):
    """What the model read out of one document."""

    stored_filename: str
    doc_type: str
    issuer: str = ""
    document_date: str = Field(default="", description="ISO date or empty if not readable")
    subject: str = ""
    amounts: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    customer_supplied: bool | None = None
    shareholders: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    age_days: int | None = None
    independent: bool | None = None
    model_request_id: str | None = None
    citation: Citation | None = None


class ClauseCondition(BaseModel):
    clause: str
    label: str
    status: Literal["met", "not_met", "exception", "not_assessed", "information"]
    finding_ids: list[str] = Field(default_factory=list)


class ModelCallNote(BaseModel):
    step: str
    purpose: str
    request_id: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float


class EvidencePack(BaseModel):
    review_id: str
    customer_ref: str
    customer_name: str
    customer_type: str
    tier: int | None
    in_scope: bool
    scope_note: str
    period_start: date
    period_end: date
    period_inferred: bool
    built_at: datetime
    model: str | None
    transactions: TransactionProfile | None
    screening: list[ScreeningItem]
    documents: list[DocumentRead]
    findings: list[Finding]
    conditions: list[ClauseCondition]
    model_calls: list[ModelCallNote]
    not_assessed: list[str]
    request_ids: list[str]
    audit_log: str | None = None
    recorded_outcome: str | None = Field(default=None, description="The analyst's recorded outcome, if the review is completed")
    recorded_clauses: list[str] = Field(default_factory=list)
    recorded_rationale: str | None = None
    recorded_analyst: str | None = None

    def findings_for(self, clause_prefix: str) -> list[Finding]:
        return [f for f in self.findings if f.clause.startswith(clause_prefix)]


class CheckFlag(BaseModel):
    code: str
    clause: str
    severity: Severity
    detail: str
    finding_ids: list[str] = Field(default_factory=list)


class CheckReport(BaseModel):
    """The pre-submit check of an analyst's recorded outcome against the pack."""

    review_id: str
    recorded_outcome: str
    clauses_cited: list[str]
    rationale_chars: int
    flags: list[CheckFlag]
    rationale_faithfulness: float | None = None
    unsupported_statements: list[str] = Field(default_factory=list)
    clean: bool
    built_at: datetime
    model_calls: list[ModelCallNote] = Field(default_factory=list)
