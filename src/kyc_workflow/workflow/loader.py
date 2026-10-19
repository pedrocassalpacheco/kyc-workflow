"""load_case: pull everything the five sources hold for one review, through the MCP server.

Clause 4.1 lists what a review must have regard to: the customer record, the
twelve-month transaction summary, current screening for the customer and
each beneficial owner, prior case history, and the documents held. This
loader fetches exactly those, keeps the bank's request id on every record,
and never writes anything.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from kyc_workflow.chat.mcp_client import RecordsClient
from kyc_workflow.mcp_server.ids import customer_ref_variants
from kyc_workflow.workflow.models import CaseFile, Citation, DocumentRecord, Record
from kyc_workflow.workflow.policy import Policy

DOC_TYPES = {
    "employment-letter": "employment letter", "payslip-extract": "payslip extract", "sof-letter": "source of funds letter",
    "acra-business-profile": "ACRA business profile", "certificate-of-incorporation": "certificate of incorporation",
    "financial-statement-extract": "financial statement extract", "bank-reference-letter": "bank reference letter",
    "remittance-cover-note": "remittance cover note", "audited-fs-extract": "audited financial statements extract",
    "management-accounts-extract": "management accounts extract",
}


class LoadError(Exception):
    pass


def doc_type_of(original_filename: str) -> str:
    stem = original_filename.rsplit(".", 1)[0]
    stem = stem.rsplit("-", 1)[0] if stem.rsplit("-", 1)[-1].isdigit() else stem
    return DOC_TYPES.get(stem, stem.replace("-", " "))


class CaseLoader:
    def __init__(self, records: RecordsClient, policy: Policy) -> None:
        self.records = records
        self.policy = policy

    async def _call(self, tool: str, **args: Any) -> tuple[dict[str, Any] | None, list[str], str | None]:
        result = await self.records.call(tool, args)
        if result.is_error:
            return None, [], result.text
        try:
            payload = json.loads(result.text)
        except ValueError:
            return None, result.request_ids, "unparseable tool result"
        return payload, list(result.request_ids or payload.get("source", {}).get("request_ids", [])), None

    @staticmethod
    def _cite(system: str, dataset: str, request_ids: list[str], record_id: str | None = None, **extra: Any) -> Citation:
        return Citation(system=system, dataset=dataset, record_id=record_id,
                        request_id=request_ids[0] if request_ids else None, **extra)

    async def load(self, review_id: str) -> CaseFile:
        request_ids: list[str] = []

        # -- the review row --------------------------------------------------------------
        payload, rids, err = await self._call("get_review", review_id=review_id)
        request_ids += rids
        review: Record | None = None
        matched_id: str | None = None
        customer_ref: str | None = None
        period_start = period_end = None
        period_from_row = False
        tier = None
        if payload:
            row = payload["review"]
            matched_id = payload["matched_id"]
            review = Record(data=row, citation=self._cite("review-worklist", "reviews_due.xlsx", rids, matched_id))
            customer_ref = row.get("customer_ref") or None
            tier = int(row["risk_tier_code"]) if str(row.get("risk_tier_code") or "").isdigit() else None
            if row.get("period_start") and row.get("period_end"):
                period_start, period_end = date.fromisoformat(row["period_start"][:10]), date.fromisoformat(row["period_end"][:10])
                period_from_row = True
            elif row.get("due_date"):
                period_end = date.fromisoformat(row["due_date"][:10])
                period_start = period_end.replace(year=period_end.year - 1) + timedelta(days=1)
        else:
            # Not on the worklist: the document index still knows the customer.
            docs, drids, _ = await self._call("list_documents", review_id=review_id)
            request_ids += drids
            if docs and docs["rows"]:
                customer_ref = docs["rows"][0]["customer_id"]
        if not customer_ref:
            raise LoadError(f"review {review_id!r} is neither on the worklist nor in the document index: {err}")

        # -- customer master ------------------------------------------------------------
        cust, rids, err = await self._call("get_customer", customer_ref=customer_ref)
        if not cust:
            raise LoadError(f"customer {customer_ref!r} not found: {err}")
        request_ids += rids
        customer = Record(data=cust["customer"], citation=self._cite("customer-master", "customers", rids, cust["matched_ref"]))
        matched_ref = cust["matched_ref"]

        async def listing(tool: str, system: str, dataset: str, key: str, **args: Any) -> list[Record]:
            payload, rids, _ = await self._call(tool, **args)
            if not payload:
                return []
            request_ids.extend(rids)
            return [Record(data=r, citation=self._cite(system, dataset, rids, r.get(key))) for r in payload["rows"]]

        accounts = await listing("list_accounts", "customer-master", "accounts", "account_number", customer_ref=matched_ref)
        owners = await listing("list_beneficial_owners", "customer-master", "beneficial_owners", "bo_id", customer_ref=matched_ref)
        officers = await listing("list_officers", "customer-master", "officers", "officer_id", customer_ref=matched_ref)
        hits = await listing("list_screening_hits", "screening", "screening_hits", "hit_id", customer_ref=matched_ref)
        cases = await listing("list_cases", "case-history", "case_history", "case_id", customer_ref=matched_ref)

        # -- prior reviews and their write-ups --------------------------------------------
        prior_reviews = [r for r in await listing("list_reviews", "review-worklist", "reviews_due.xlsx", "review_id",
                                                  customer_ref=matched_ref) if r.get("review_id") != matched_id]
        prior_notes: list[Record] = []
        for pr in prior_reviews:
            if pr.get("status") == "completed":
                note, rids, _ = await self._call("get_review_note", review_id=pr.get("review_id"))
                if note:
                    request_ids += rids
                    prior_notes.append(Record(data=note["note"], citation=self._cite("case-history", "case_notes", rids, pr.get("review_id"))))
        recorded_note = None
        if review is not None and review.get("status") == "completed":
            note, rids, _ = await self._call("get_review_note", review_id=matched_id)
            if note:
                request_ids += rids
                recorded_note = Record(data=note["note"], citation=self._cite("case-history", "case_notes", rids, matched_id))

        # -- documents held on file: this review's and the customer's earlier ones ---------
        seen: dict[str, dict[str, Any]] = {}
        for args in ({"review_id": matched_id or review_id}, {"customer_id": f"CIF-{''.join(ch for ch in matched_ref if ch.isdigit())}"}):
            payload, rids, _ = await self._call("list_documents", **args)
            if payload:
                request_ids += rids
                for row in payload["rows"]:
                    seen.setdefault(row["stored_filename"], row)
        documents: list[DocumentRecord] = []
        for row in seen.values():
            doc, rids, _ = await self._call("get_document", stored_filename=row["stored_filename"])
            if not doc:
                continue
            request_ids += rids
            documents.append(DocumentRecord(
                stored_filename=row["stored_filename"], original_filename=row["original_filename"],
                doc_type=doc_type_of(row["original_filename"]), review_id=row.get("review_id"), customer_id=row.get("customer_id"),
                belongs_to_this_review=row.get("review_id") in (matched_id, review_id), text=doc["text"],
                citation=self._cite("document-store", "documents", rids, document=row["stored_filename"]),
            ))

        # -- transactions over the review period ----------------------------------------------
        period_inferred = not period_from_row
        if period_start is None:
            period_end = date(2026, 6, 30)
            period_start = date(2025, 7, 1)
        transactions: list[Record] = []
        for acct in accounts:
            payload, rids, _ = await self._call("list_transactions", account_number=acct.get("account_number"),
                                                date_from=period_start.isoformat(), date_to=period_end.isoformat())
            if payload:
                request_ids += rids
                for i, row in enumerate(payload["rows"]):
                    transactions.append(Record(data=row, citation=self._cite(
                        "transaction-summary", row.get("source_file", "transactions_*"), rids, f"{row.get('account')}#{row.get('date')}#{i}")))

        in_scope = tier in self.policy.rules.in_scope_tiers if tier is not None else True
        scope_note = ("" if in_scope else f"risk tier {tier} is outside the low and medium scope of this proof of concept; "
                      "the pack is built for information only and must not be used to work the file")
        if tier is None:
            scope_note = "risk tier not recorded on the worklist row; scope assumed low or medium"

        return CaseFile(
            review_id=review_id, matched_review_id=matched_id, review=review, customer_ref=matched_ref,
            period_start=period_start, period_end=period_end, period_inferred=period_inferred, tier=tier,
            in_scope=in_scope, scope_note=scope_note, customer=customer, accounts=accounts, beneficial_owners=owners,
            officers=officers, screening_hits=hits, cases=cases, prior_reviews=prior_reviews, prior_notes=prior_notes,
            recorded_note=recorded_note, documents=documents, transactions=transactions,
            request_ids=list(dict.fromkeys(request_ids)), loaded_at=datetime.now(timezone.utc),
        )
