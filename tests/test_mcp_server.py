"""The MCP server over the bank's HTTP API, end to end but local.

A real `bank_api/server.py` process serves the synthetic fixture export in
tests/fixtures/bank_export; the MCP server is driven through the SDK's
in-memory client. So every tool call here goes MCP -> HTTP -> CSV, the same
path the harness will use, with no network beyond localhost.
"""

from __future__ import annotations

import json

import pytest
from mcp.client import Client

from kyc_workflow.mcp_server import HIDDEN_DATASETS, BankApi, BankApiError, build_server
from kyc_workflow.mcp_server.ids import account_number_variants, customer_ref_variants

from tests.conftest import BANK_API_KEY as API_KEY, free_port as _free_port

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def api(bank_api_url) -> BankApi:
    return BankApi(bank_api_url, API_KEY)


@pytest.fixture(scope="module")
def server(api):
    return build_server(api)


def payload(result) -> dict:
    """Structured content if the SDK produced it, else the JSON text block."""
    if result.structured_content:
        return result.structured_content
    return json.loads(result.content[0].text)


# -- identifier helpers (pure) ------------------------------------------------

@pytest.mark.parametrize("given, expected_first", [
    ("CIF-1000001", "CIF-1000001"),
    ("CIF1000001", "CIF1000001"),
    ("1000001", "1000001"),
])
def test_customer_ref_variants_cover_all_shapes(given, expected_first):
    variants = customer_ref_variants(given)
    assert variants[0] == expected_first
    assert set(variants) == {"CIF-1000001", "CIF1000001", "1000001"}


def test_account_number_variants():
    assert account_number_variants("0001234567") == ["0001234567", "1234567"]
    assert account_number_variants("1234567") == ["1234567", "0001234567"]


# -- the HTTP client -----------------------------------------------------------

def test_http_client_sends_key_and_gets_request_id_back(api):
    page = api.page("customers", {"customer_ref": "CIF-1000001"})
    assert page.rows[0]["legal_name"] == "Tan Mei Ling"
    assert len(page.request_id) == 36  # our uuid, echoed by the server


def test_http_client_wrong_key_is_an_error(bank_api_url):
    with pytest.raises(BankApiError) as excinfo:
        BankApi(bank_api_url, "wrong").page("customers")
    assert excinfo.value.status == 401


def test_http_client_pages_through_everything(api, monkeypatch):
    import kyc_workflow.mcp_server.http_client as hc
    monkeypatch.setattr(hc, "MAX_PAGE", 2)
    found = api.rows("transactions_2025H2")
    assert len(found.rows) == 11
    assert len(found.request_ids) == 6  # six pages of two


# -- tool surface --------------------------------------------------------------

async def test_tool_surface_is_read_only_and_well_described(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    assert names == {
        "get_review", "list_reviews",
        "get_customer", "list_accounts", "list_beneficial_owners", "list_officers",
        "list_screening_hits", "get_screening_hit",
        "list_cases", "get_case", "get_review_note",
        "list_documents", "get_document",
        "list_transactions", "list_transaction_files",
    }
    for tool in tools:
        assert tool.name.split("_")[0] in {"get", "list"}, tool.name
        desc = tool.description or ""
        assert desc.startswith("["), f"{tool.name} must name its record system first"
        assert "Use this" in desc, f"{tool.name} must say when to use it"
        assert len(desc) > 120, f"{tool.name} description too thin for routing"


async def test_qa_sample_is_not_reachable(server):
    async with Client(server) as client:
        tools = (await client.list_tools()).tools
    blob = " ".join((t.name + " " + (t.description or "")) for t in tools).lower()
    for hidden in HIDDEN_DATASETS:
        assert hidden not in blob
    assert "overturn" not in blob


# -- review worklist ------------------------------------------------------------

@pytest.mark.parametrize("given", ["VGB-PR-2026-0001", "PR2026-0001", "vgb_pr_26_0001", "0001"])
async def test_get_review_resolves_every_id_shape_and_skips_dummy_rows(server, given):
    async with Client(server) as client:
        out = payload(await client.call_tool("get_review", {"review_id": given}))
        listed = payload(await client.call_tool("list_reviews", {"customer_ref": "CIF1000001"}))
        pending = payload(await client.call_tool("list_reviews", {"status": "pending"}))
        missing = await client.call_tool("get_review", {"review_id": "DUMMY000001"})
    assert out["review"]["customer_ref"] == "CIF-1000001" and out["review"]["period_start"] == "2025-01-01"
    assert out["matched_id"] == "VGB-PR-2026-0001" and out["source"]["dataset"] == "reviews_due.xlsx"
    assert {r["review_id"] for r in listed["rows"]} == {"VGB-PR-2026-0001", "VGB-PR-2024-0009"}
    assert [r["review_id"] for r in pending["rows"]] == ["VGB-PR-2026-0003"]
    assert missing.is_error


# -- customer master -----------------------------------------------------------

@pytest.mark.parametrize("given, stored", [
    ("CIF-1000001", "CIF-1000001"),
    ("CIF1000001", "CIF-1000001"),     # file uses the dashed shape
    ("CIF-1000002", "CIF1000002"),     # file uses the undashed shape
    ("CIF-1000003", "1000003"),        # file uses bare digits
])
async def test_get_customer_resolves_identifier_shapes(server, given, stored):
    async with Client(server) as client:
        out = payload(await client.call_tool("get_customer", {"customer_ref": given}))
    assert out["customer"]["customer_ref"] == stored
    assert out["matched_ref"] == stored
    assert out["source"]["system"] == "customer-master"
    assert out["source"]["dataset"] == "customers"
    assert out["source"]["request_ids"]


async def test_get_customer_unknown_is_a_tool_error(server):
    async with Client(server) as client:
        result = await client.call_tool("get_customer", {"customer_ref": "CIF-0000000"})
    assert result.is_error
    assert "no customer record" in result.content[0].text


async def test_customer_master_listings(server):
    async with Client(server) as client:
        accounts = payload(await client.call_tool("list_accounts", {"customer_ref": "CIF-1000002"}))
        owners = payload(await client.call_tool("list_beneficial_owners", {"customer_ref": "CIF-1000002"}))
        officers = payload(await client.call_tool("list_officers", {"customer_ref": "CIF-1000002"}))
        none = payload(await client.call_tool("list_beneficial_owners", {"customer_ref": "CIF-1000001"}))
    assert [a["account_number"] for a in accounts["rows"]] == ["0007654321"]
    assert owners["rows"][0]["bo_name"] == "Tan K. H." and owners["count"] == 1
    assert officers["rows"][0]["role"] == "Director"
    assert none["rows"] == [] and none["matched_ref"] is None


# -- screening -----------------------------------------------------------------

async def test_screening_hits_include_undispositioned(server):
    async with Client(server) as client:
        out = payload(await client.call_tool("list_screening_hits", {"customer_ref": "1000001"}))
        one = payload(await client.call_tool("get_screening_hit", {"hit_id": "H-2"}))
    statuses = {h["hit_id"]: h["disposition_status"] for h in out["rows"]}
    assert statuses == {"H-1": "FALSE", "H-2": ""}
    assert one["hit"]["category"] == "sanctions"
    assert one["source"]["system"] == "screening"


# -- case history --------------------------------------------------------------

async def test_case_history_and_review_notes(server):
    async with Client(server) as client:
        cases = payload(await client.call_tool("list_cases", {"customer_ref": "CIF-1000003"}))
        case = payload(await client.call_tool("get_case", {"case_id": "CM-2026-0002"}))
        note = payload(await client.call_tool("get_review_note", {"review_id": "PR2026-0002"}))
    assert cases["rows"][0]["outcome"] == "rfi_issued" and cases["rows"][0]["closed_dt"] == ""
    assert case["case"]["case_type"] == "rfi"
    assert note["note"]["clauses_cited"] == ""  # the no-clause case
    assert note["source"]["dataset"] == "case_notes"


# -- document store ------------------------------------------------------------

async def test_documents_by_review_and_by_customer_then_read(server):
    async with Client(server) as client:
        by_review = payload(await client.call_tool("list_documents", {"review_id": "VGB-PR-2026-0001"}))
        by_customer = payload(await client.call_tool("list_documents", {"customer_id": "CIF-1000002"}))
        doc = payload(await client.call_tool("get_document", {"stored_filename": by_review["rows"][0]["stored_filename"]}))
        unindexed = payload(await client.call_tool("get_document", {"stored_filename": "VGB-PR-2026-0003__sof-letter-9.txt"}))
        missing = await client.call_tool("get_document", {"stored_filename": "nope.txt"})
        neither = await client.call_tool("list_documents", {})
    assert by_review["rows"][0]["original_filename"] == "sof-letter-1.txt"
    assert by_customer["rows"][0]["stored_filename"] == "1000002_acra_business_profile_1.txt"
    assert "388,000.00" in doc["text"]
    assert doc["source"]["stored_filename"] == "1000001_sof_letter_1.txt"
    assert unindexed["text"].startswith("UNINDEXED")
    assert missing.is_error and neither.is_error


# -- transaction summary -------------------------------------------------------

async def test_transactions_unified_across_schemas_and_zero_padding(server):
    async with Client(server) as client:
        out = payload(await client.call_tool("list_transactions", {"account_number": "0001234567"}))
    assert out["matched_account"] in ("0001234567", "1234567")
    assert out["files_searched"] == ["transactions_2025H1", "transactions_2025H2", "transactions_2026H1"]
    rows = out["rows"]
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates) and dates[0] == "2025-01-10" and dates[-1] == "2026-02-10"
    big = next(r for r in rows if r["amount"] == 388000.0)
    assert big == {
        "date": "2025-07-24", "account": "1234567", "amount": 388000.0, "direction": "credit",
        "counterparty": "Lee & Partners LLC client account", "counterparty_country": "SG",
        "source_file": "transactions_2025H2",
    }
    assert {r["direction"] for r in rows} == {"credit", "debit"}
    assert next(r for r in rows if r["date"] == "2026-01-10")["source_file"] == "transactions_2026H1"
    assert all(set(r.keys()) == set(rows[0].keys()) for r in rows)


async def test_transactions_date_window_and_unknown_account(server):
    async with Client(server) as client:
        window = payload(await client.call_tool(
            "list_transactions", {"account_number": "1234567", "date_from": "2026-01-01", "date_to": "2026-01-31"}))
        nothing = payload(await client.call_tool("list_transactions", {"account_number": "0000000000"}))
        files = payload(await client.call_tool("list_transaction_files", {}))
    assert [r["date"] for r in window["rows"]] == ["2026-01-10"]
    assert nothing["rows"] == [] and nothing["matched_account"] is None
    assert files["files"] == ["transactions_2025H1", "transactions_2025H2", "transactions_2026H1"]


# -- failure of the bank api ----------------------------------------------------

async def test_bank_api_down_is_a_tool_error_not_a_crash():
    dead = build_server(BankApi(f"http://127.0.0.1:{_free_port()}", API_KEY, timeout_s=1))
    async with Client(dead) as client:
        result = await client.call_tool("get_customer", {"customer_ref": "CIF-1000001"})
    assert result.is_error
    assert "unreachable" in result.content[0].text
