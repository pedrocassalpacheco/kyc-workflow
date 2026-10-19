"""Routing cases: an analyst-style request and the tool call(s) it should map to.

Each case is a prompt, the reference tool calls (name and the arguments that
must match exactly), and whether order matters. A case with no reference
calls is a negative: the right behaviour is to call nothing, because the
information is not available through the server (QA outcomes are hidden by
design).
"""

CASES: list[dict] = [
    {
        "id": "review-row",
        "prompt": "What is the review period and risk tier for review VGB-PR-2026-1173?",
        "expected": [{"name": "get_review", "args": {"review_id": "VGB-PR-2026-1173"}}],
    },
    {
        "id": "previous-reviews",
        "prompt": "Which earlier periodic reviews has customer CIF-2911315 had?",
        "expected": [{"name": "list_reviews", "args": {"customer_ref": "CIF-2911315"}}],
    },
    {
        "id": "customer-record",
        "prompt": "Pull up the customer record for CIF-1004823.",
        "expected": [{"name": "get_customer", "args": {"customer_ref": "CIF-1004823"}}],
    },
    {
        "id": "accounts",
        "prompt": "Which accounts does customer CIF1004823 hold?",
        "expected": [{"name": "list_accounts", "args": {"customer_ref": "CIF1004823"}}],
    },
    {
        "id": "beneficial-owners",
        "prompt": "Who are the beneficial owners on file for CIF-3098094?",
        "expected": [{"name": "list_beneficial_owners", "args": {"customer_ref": "CIF-3098094"}}],
    },
    {
        "id": "officers",
        "prompt": "List the directors and other officers recorded for CIF-3098094.",
        "expected": [{"name": "list_officers", "args": {"customer_ref": "CIF-3098094"}}],
    },
    {
        "id": "screening-hits",
        "prompt": "Show every screening hit for CIF-6244597, including any that still have no disposition.",
        "expected": [{"name": "list_screening_hits", "args": {"customer_ref": "CIF-6244597"}}],
    },
    {
        "id": "screening-hit-by-id",
        "prompt": "Give me the full record of screening hit H-10613.",
        "expected": [{"name": "get_screening_hit", "args": {"hit_id": "H-10613"}}],
    },
    {
        "id": "prior-cases",
        "prompt": "What prior cases, RFIs or alerts does CIF-1004823 have in Castellan?",
        "expected": [{"name": "list_cases", "args": {"customer_ref": "CIF-1004823"}}],
    },
    {
        "id": "case-by-id",
        "prompt": "Open case CM-2020-1062 and tell me its outcome.",
        "expected": [{"name": "get_case", "args": {"case_id": "CM-2020-1062"}}],
    },
    {
        "id": "review-note",
        "prompt": "What did the analyst write up on review VGB-PR-2026-0041, and which POL-042 clauses were cited?",
        "expected": [{"name": "get_review_note", "args": {"review_id": "VGB-PR-2026-0041"}}],
    },
    {
        "id": "documents-for-review",
        "prompt": "What documents are on file for review VGB-PR-2026-0041?",
        "expected": [{"name": "list_documents", "args": {"review_id": "VGB-PR-2026-0041"}}],
    },
    {
        "id": "read-document",
        "prompt": "Read the document 1004823_employment_letter_1.txt and tell me its date.",
        "expected": [{"name": "get_document", "args": {"stored_filename": "1004823_employment_letter_1.txt"}}],
    },
    {
        "id": "transactions-window",
        "prompt": "List all credits and debits on account 5583716687 during calendar year 2025.",
        "expected": [{"name": "list_transactions", "args": {
            "account_number": "5583716687", "date_from": "2025-01-01", "date_to": "2025-12-31"}}],
    },
    {
        "id": "transaction-files",
        "prompt": "Which half-year transaction extracts are available?",
        "expected": [{"name": "list_transaction_files", "args": {}}],
    },
    {
        "id": "two-lookups",
        "prompt": "Get me both the customer record and the list of accounts for CIF-1004823.",
        "expected": [
            {"name": "get_customer", "args": {"customer_ref": "CIF-1004823"}},
            {"name": "list_accounts", "args": {"customer_ref": "CIF-1004823"}},
        ],
        "ordered": False,
    },
    {
        "id": "qa-not-available",
        "prompt": "Did QA overturn review VGB-PR-2026-0078, and what reason did they record?",
        "expected": [],
        "note": "QA outcomes are deliberately not exposed; the right move is to call nothing and say so.",
    },
]
