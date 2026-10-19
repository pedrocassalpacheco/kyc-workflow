"""The routing eval's plumbing, offline: tool conversion and Ragas scoring with
canned predictions. The model call itself is exercised by `make eval-routing`."""

import pytest

from evals.routing.cases import CASES
from evals.routing.run import load_tools, score_case


def case(case_id: str) -> dict:
    return next(c for c in CASES if c["id"] == case_id)


def test_cases_are_well_formed_and_reference_real_tools():
    _, tools = load_tools("inproc")
    names = {t.name for t in tools}
    assert len(CASES) >= 10
    assert len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        for e in c["expected"]:
            assert e["name"] in names, f"{c['id']} references unknown tool {e['name']}"
            schema = next(t for t in tools if t.name == e["name"]).input_schema
            assert set(e["args"]) <= set(schema.get("properties", {})), f"{c['id']} has an argument not in the schema"


def test_tool_definitions_keep_descriptions_and_schemas():
    instructions, tools = load_tools("inproc")
    assert "customer master" in instructions
    assert len(tools) == 15
    for t in tools:
        assert t.description.startswith("[")
        assert t.input_schema["type"] == "object"


def test_exact_match_scores_one():
    assert score_case(case("customer-record"), [{"name": "get_customer", "args": {"customer_ref": "CIF-1004823"}}]) == 1.0


def test_wrong_tool_scores_zero():
    assert score_case(case("customer-record"), [{"name": "list_accounts", "args": {"customer_ref": "CIF-1004823"}}]) == 0.0


def test_right_tool_wrong_argument_scores_zero():
    assert score_case(case("customer-record"), [{"name": "get_customer", "args": {"customer_ref": "CIF-0000000"}}]) == 0.0


def test_partial_arguments_score_partially():
    predicted = [{"name": "list_transactions", "args": {"account_number": "5583716687", "date_from": "2025-01-01"}}]
    score = score_case(case("transactions-window"), predicted)
    assert 0.0 < score < 1.0
    assert score == pytest.approx(2 / 3)


def test_unordered_pair_scores_one_in_either_order():
    pair = case("two-lookups")
    forward = [{"name": "get_customer", "args": {"customer_ref": "CIF-1004823"}},
               {"name": "list_accounts", "args": {"customer_ref": "CIF-1004823"}}]
    assert score_case(pair, forward) == 1.0
    assert score_case(pair, list(reversed(forward))) == 1.0


def test_negative_case_rewards_calling_nothing():
    negative = case("qa-not-available")
    assert score_case(negative, []) == 1.0
    assert score_case(negative, [{"name": "get_review_note", "args": {"review_id": "VGB-PR-2026-0078"}}]) == 0.0
