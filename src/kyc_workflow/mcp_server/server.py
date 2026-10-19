"""One MCP server over the bank's reference data API.

The bank exposes its five record systems as separate MCP servers inside the
network. Here they are one server, `vgb-records`, with tools grouped by
system so the shape stays visible without five processes. Every tool is a
thin read-only call to `bank_api/server.py`; that HTTP server is used as
delivered, never bypassed.

Tool descriptions are written for routing: each says which record system it
reads, when to use it, what to give it, what comes back, and what it will
not do. The harness picks tools in code, but the same descriptions let a
model or a person pick correctly too.

Every result carries a `source` block (system, dataset, the request ids the
bank's API echoed) so a statement built from the result can cite exactly
where it came from.

Deliberately not exposed: `qa_sample.csv`. It is the QA function's log of
overturns, the evaluation ground truth. The workflow must never see it; the
evaluation harness reads it from disk.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from kyc_workflow.mcp_server.http_client import BankApi, BankApiError
from kyc_workflow.mcp_server.ids import account_number_variants, customer_ref_variants, review_id_variants

SERVER_NAME = "vgb-records"

INSTRUCTIONS = """\
Read-only access to Veridian Global Bank's five KYC record systems, as a
KYC analyst sees them during a periodic review:

  review worklist      get_review, list_reviews
  customer master      get_customer, list_accounts, list_beneficial_owners, list_officers
  screening            list_screening_hits, get_screening_hit
  case history         list_cases, get_case, get_review_note
  document store       list_documents, get_document
  transaction summary  list_transactions, list_transaction_files

Start from a customer reference (CIF) with get_customer, then list_accounts
for the account numbers that list_transactions needs. Identifiers come in
several shapes (CIF-1234567, CIF1234567, CIF123456, 1234567); every lookup
tries each shape and reports the one that matched. Nothing here writes,
rates, or decides; results are records with a `source` block for citation.
"""

TRANSACTION_FILES = ("transactions_2024H2", "transactions_2025H1", "transactions_2025H2", "transactions_2026H1")

# Column aliases across the four transaction extracts (2026H1 changed names).
TXN_COLUMNS = {
    "date": ("txn_dt", "transaction_date"),
    "account": ("acct", "account_number"),
    "amount": ("amt", "amount"),
    "direction": ("dr_cr", "direction"),
    "counterparty": ("cpty", "counterparty_name"),
    "counterparty_country": ("cpty_ctry", "counterparty_country"),
}

HIDDEN_DATASETS = ("qa_sample",)


def _source(system: str, dataset: str, request_ids: Iterable[str], **extra: Any) -> dict[str, Any]:
    return {"system": system, "dataset": dataset, "request_ids": list(request_ids), **extra}


def _call(fn):
    """Run a bank API call; turn failures into tool errors that keep the request id."""
    try:
        return fn()
    except BankApiError as err:
        raise ToolError(f"bank api: {err} (request {err.request_id})") from err


def _by_customer(api: BankApi, dataset: str, customer_ref: str, column: str = "customer_ref"):
    """Rows of `dataset` for a customer, trying each identifier shape in turn."""
    tried: list[str] = []
    found = None
    for variant in customer_ref_variants(customer_ref):
        tried.append(variant)
        found = _call(lambda: api.rows(dataset, {column: variant}))
        if found.rows:
            return found, variant, tried
    return found, None, tried


def _listing(system: str, dataset: str, found, matched: str | None, tried: list[str]) -> dict[str, Any]:
    return {
        "rows": found.rows,
        "count": len(found.rows),
        "matched_ref": matched,
        "tried": tried,
        "source": _source(system, dataset, found.request_ids),
    }


def _normalise_txn(row: dict[str, str], source_file: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, aliases in TXN_COLUMNS.items():
        out[key] = next((row[a] for a in aliases if a in row), None)
    try:
        out["amount"] = float((out["amount"] or "").replace(",", ""))
    except ValueError:
        out["amount"] = None
    direction = (out["direction"] or "").strip().lower()
    out["direction"] = {"c": "credit", "d": "debit"}.get(direction, direction or None)
    out["source_file"] = source_file
    return out


def build_server(api: BankApi) -> MCPServer:
    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS)

    # -- review worklist (reviews_due.xlsx) ------------------------------------

    @server.tool()
    def get_review(review_id: str) -> dict[str, Any]:
        """[Review worklist] One periodic review from the worklist, by review id.

        Use this first when working a review: it gives the customer reference,
        the review period (period_start, period_end), the due date, the risk
        tier code (1 low, 2 standard, 3 elevated, 4 high), the assigned
        analyst and the status (completed or pending). Review ids come in
        several shapes (VGB-PR-2026-0041, PR2026-0041, vgb_pr_26_0041, 0041);
        every shape is tried. Pending reviews may have no period yet. Errors
        if the id is not on the worklist.
        """
        rows, rid = _call(api.worklist)
        tried = review_id_variants(review_id)
        for variant in tried:
            match = next((r for r in rows if r["review_id"] == variant), None)
            if match:
                return {"review": match, "matched_id": variant,
                        "source": _source("review-worklist", "reviews_due.xlsx", [rid])}
        raise ToolError(f"no review {review_id!r} on the worklist; tried {tried}")

    @server.tool()
    def list_reviews(customer_ref: str | None = None, status: str | None = None) -> dict[str, Any]:
        """[Review worklist] Reviews on the worklist for one customer, or by status.

        Use this to find a customer's previous reviews (then get_review_note
        for their write-ups) or to list pending work. Give a customer_ref
        (any CIF shape) and/or a status (completed, pending). Rows carry the
        same fields as get_review. Without filters it returns the whole
        worklist, which is large.
        """
        rows, rid = _call(api.worklist)
        if customer_ref:
            wanted = set(customer_ref_variants(customer_ref))
            rows = [r for r in rows if r["customer_ref"] in wanted]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        return {"rows": rows, "count": len(rows), "source": _source("review-worklist", "reviews_due.xlsx", [rid])}

    # -- customer master ---------------------------------------------------

    @server.tool()
    def get_customer(customer_ref: str) -> dict[str, Any]:
        """[Customer master] The customer record for one customer reference (CIF).

        Use this first on any review: it gives legal name, customer type
        (individual or entity), address, risk rating, onboarding date, declared
        turnover, business activity, markets, occupation, employer, declared
        source of funds, PEP flag, nationality and, for entities, jurisdiction,
        incorporation date and registration number. Give any CIF shape; the
        result says which shape the file used (`matched_ref`). Returns exactly
        one record or an error if the customer does not exist. Does not include
        accounts, owners or officers; use the list_* tools for those.
        """
        found, matched, tried = _by_customer(api, "customers", customer_ref)
        if not found.rows:
            raise ToolError(f"no customer record for {customer_ref!r}; tried {tried}")
        return {"customer": found.rows[0], "matched_ref": matched,
                "source": _source("customer-master", "customers", found.request_ids)}

    @server.tool()
    def list_accounts(customer_ref: str) -> dict[str, Any]:
        """[Customer master] All accounts held by one customer.

        Use this to get the account numbers that list_transactions needs, and
        to see product type, open date and status (OPEN or otherwise). One row
        per account. An empty list means no accounts are recorded, not an error.
        Does not include balances or transactions.
        """
        return _listing("customer-master", "accounts", *_by_customer(api, "accounts", customer_ref))

    @server.tool()
    def list_beneficial_owners(customer_ref: str) -> dict[str, Any]:
        """[Customer master] Beneficial owners recorded on the customer master for one customer.

        Use this for the ownership check on an entity customer: name,
        effective percentage, basis (direct or indirect), nationality and
        birth date per owner. This is what the bank's own record says; compare
        it with the registry extract from the document store to find changes
        the record has not picked up. Empty for individuals. Does not screen
        the owners; use list_screening_hits for that.
        """
        return _listing("customer-master", "beneficial_owners", *_by_customer(api, "beneficial_owners", customer_ref))

    @server.tool()
    def list_officers(customer_ref: str) -> dict[str, Any]:
        """[Customer master] Directors, secretaries and other officers recorded for one entity customer.

        Use this alongside list_beneficial_owners for the ownership and control
        check: officer name, role, nationality, appointment date and a masked
        id number. Officers are connected parties, not owners. Empty for
        individuals.
        """
        return _listing("customer-master", "officers", *_by_customer(api, "officers", customer_ref))

    # -- screening -----------------------------------------------------------

    @server.tool()
    def list_screening_hits(customer_ref: str) -> dict[str, Any]:
        """[Screening] Every screening hit on one customer and their connected parties, in all disposition states.

        Use this for the screening step of a review. Each hit gives the
        screened subject and role, the matched list name, category (sanctions,
        PEP, adverse media), match strength and score, listed name, date of
        birth and nationality, media headline and source where relevant, the
        disposition status, reason code and remark, and when it was screened.
        Hits with an empty disposition are undispositioned and need a reason
        before the file can close. An empty list means no hits. Does not run a
        new screen.
        """
        return _listing("screening", "screening_hits", *_by_customer(api, "screening_hits", customer_ref))

    @server.tool()
    def get_screening_hit(hit_id: str) -> dict[str, Any]:
        """[Screening] One screening hit by its hit id (for example H-10613).

        Use this when you already have a hit id from list_screening_hits or a
        prior review and need its full record again. Returns one hit or an
        error if the id is unknown.
        """
        found = _call(lambda: api.rows("screening_hits", {"hit_id": hit_id}))
        if not found.rows:
            raise ToolError(f"no screening hit {hit_id!r}")
        return {"hit": found.rows[0], "source": _source("screening", "screening_hits", found.request_ids)}

    # -- case history (Castellan) --------------------------------------------

    @server.tool()
    def list_cases(customer_ref: str) -> dict[str, Any]:
        """[Case history] Prior cases on one customer from Castellan: past reviews, RFIs, alerts and event-driven cases.

        Use this for "what happened last time": each case has a case id,
        type, alert type, opened and closed dates, outcome and a narrative.
        Look here for an open RFI (a case whose outcome is rfi_issued with no
        closing) and for the previous periodic review. Does not include the
        full review write-up; use get_review_note with the review id for that.
        """
        return _listing("case-history", "case_history", *_by_customer(api, "case_history", customer_ref))

    @server.tool()
    def get_case(case_id: str) -> dict[str, Any]:
        """[Case history] One Castellan case by its case id (for example CM-2020-1062).

        Use this when a case id is already known and you need its outcome and
        narrative. Returns one case or an error if the id is unknown.
        """
        found = _call(lambda: api.rows("case_history", {"case_id": case_id}))
        if not found.rows:
            raise ToolError(f"no case {case_id!r}")
        return {"case": found.rows[0], "source": _source("case-history", "case_history", found.request_ids)}

    @server.tool()
    def get_review_note(review_id: str) -> dict[str, Any]:
        """[Case history] The completed write-up of one periodic review, by review id (for example VGB-PR-2026-0041).

        Use this to read what the analyst concluded on a past review: analyst
        id, review date, outcome code, the full rationale text, the POL-042
        clauses cited (may be empty) and who checked it. Review ids come in
        several shapes in this file (VGB-PR-2026-0041, PR2026-0014,
        vgb_pr_26_0032, 0032); give the id exactly as the index or the case
        shows it. Returns one note or an error. Does not include QA's view of
        the review; that is not available through this server.
        """
        found = _call(lambda: api.rows("case_notes", {"review_id": review_id}))
        if not found.rows:
            raise ToolError(f"no review note {review_id!r}")
        return {"note": found.rows[0], "source": _source("case-history", "case_notes", found.request_ids)}

    # -- document store --------------------------------------------------------

    @server.tool()
    def list_documents(review_id: str | None = None, customer_id: str | None = None) -> dict[str, Any]:
        """[Document store] Index entries for the documents on file for a review or a customer.

        Use this to find what evidence exists before reading any of it. Give a
        review id (VGB-PR-2026-0041) or a customer id (CIF-1004823, this file
        always uses the CIF- shape), or both. Each entry gives the stored
        filename to pass to get_document, the review and customer it belongs
        to, and the original filename, whose name shows the document type
        (employment letter, payslip extract, source-of-funds letter, ACRA
        business profile, certificate of incorporation, financial statement
        extract, bank reference letter, remittance cover note). Some documents
        in the store are not in this index; get_document can still read them
        by filename.
        """
        if not review_id and not customer_id:
            raise ToolError("give review_id or customer_id")
        filters = {k: v for k, v in (("review_id", review_id), ("customer_id", customer_id)) if v}
        found = _call(lambda: api.rows("doc_index", filters))
        return {"rows": found.rows, "count": len(found.rows),
                "source": _source("document-store", "doc_index", found.request_ids)}

    @server.tool()
    def get_document(stored_filename: str) -> dict[str, Any]:
        """[Document store] The full text of one document, by stored filename.

        Use this to read a document found through list_documents, for example
        to take its date, issuer, parties and amounts. Documents are plain-text
        renderings of the originals and may contain OCR-style errors. Returns
        the text as-is; it does not summarise or interpret. Errors if the file
        is not in the store.
        """
        text, rid = _call(lambda: api.document(stored_filename))
        return {"stored_filename": stored_filename, "text": text,
                "source": _source("document-store", "documents", [rid], stored_filename=stored_filename)}

    # -- transaction summary ---------------------------------------------------

    @server.tool()
    def list_transactions(account_number: str, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
        """[Transaction summary] Credits and debits on one account across all half-year extracts, optionally within a date window.

        Use this for the source-of-funds and activity checks: get the account
        number from list_accounts, then call this with ISO dates (YYYY-MM-DD,
        inclusive) for the review window. Rows come back in one shape
        regardless of which extract they came from: date, account, amount (a
        number), direction (credit or debit), counterparty, counterparty
        country, and source_file. Account numbers are matched with and without
        leading zeros. Transactions on record start in December 2024; earlier
        windows return nothing. Does not aggregate; sum credits yourself.
        """
        available = set(_call(api.datasets))
        files = [f for f in TRANSACTION_FILES if f in available]
        rows: list[dict[str, Any]] = []
        request_ids: list[str] = []
        matched_account: str | None = None
        for source_file in files:
            columns = _call(lambda: api.columns(source_file))
            acct_col = next((a for a in TXN_COLUMNS["account"] if a in columns), None)
            if acct_col is None:
                continue
            for variant in account_number_variants(account_number):
                found = _call(lambda: api.rows(source_file, {acct_col: variant}))
                request_ids.extend(found.request_ids)
                if found.rows:
                    matched_account = matched_account or variant
                    rows.extend(_normalise_txn(r, source_file) for r in found.rows)
                    break
        if date_from:
            rows = [r for r in rows if r["date"] and r["date"] >= date_from]
        if date_to:
            rows = [r for r in rows if r["date"] and r["date"] <= date_to]
        rows.sort(key=lambda r: (r["date"] or "", r["source_file"]))
        return {"rows": rows, "count": len(rows), "matched_account": matched_account,
                "files_searched": files,
                "source": _source("transaction-summary", "transactions_*", request_ids)}

    @server.tool()
    def list_transaction_files() -> dict[str, Any]:
        """[Transaction summary] Which half-year transaction extracts are available (for example transactions_2025H2).

        Use this only to confirm coverage of a review window; list_transactions
        already searches every extract.
        """
        available = _call(api.datasets)
        return {"files": [f for f in TRANSACTION_FILES if f in available]}

    return server
