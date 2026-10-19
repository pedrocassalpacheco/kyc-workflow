"""The evidence pack workflow over the fixture export: real MCP server (in-process),
real policy text, real deterministic steps, and a fake model that answers each
structured prompt by schema. No network."""

import json
from pathlib import Path

import pytest

from kyc_workflow.chat import RecordsClient
from kyc_workflow.config import BankApiSettings, Settings
from kyc_workflow.gateway import FakeGateway, GatewayError, ModelRequest
from kyc_workflow.workflow import LoadError, build_pack, load_policy, pack_markdown
from kyc_workflow.workflow.steps.documents import DocumentFields
from kyc_workflow.workflow.steps.model_steps import (
    ConsistencyAssessment, CreditMatch, CreditMatches, MediaCategory, NarrativeRead, NarrativeSignal,
    PlausibilityAssessment, ReviewerNotes, Suggestion,
)
from tests.conftest import BANK_API_KEY

pytestmark = pytest.mark.anyio


def fake_model(request: ModelRequest):
    """Canned structured answers, chosen by schema and by what is in the prompt."""
    schema = request.output_schema
    user = request.user or ""
    if schema is DocumentFields:
        if "sof_letter" in user:
            return DocumentFields(issuer="Lee & Partners LLC", document_date="2025-07-24", subject="Tan Mei Ling",
                                  amounts=["SGD 388,000.00 net sale proceeds"], key_facts=["Sale of 12 Lorong 4 Toa Payoh #05-11 completed"],
                                  customer_supplied=False, shareholders=[], directors=[], illegible=[])
        if "acra" in user:
            return DocumentFields(issuer="ACRA", document_date="2026-01-14", subject="Pelican Ridge Holdings Pte Ltd", amounts=[],
                                  key_facts=["Registration 201512345K"], customer_supplied=False,
                                  shareholders=["Tan K. H. (70%)", "Corvin Capital Ltd (30%)"], directors=["Tan K. H.", "R. Varga"], illegible=[])
        return DocumentFields(issuer="Mei Heng Food Pte Ltd", document_date="2023-01-31", subject="Tan Mei Ling", amounts=["SGD 3,100.00 net pay"],
                              key_facts=["Payslip for January 2023"], customer_supplied=False, shareholders=[], directors=[], illegible=[])
    if schema is ConsistencyAssessment:
        return ConsistencyAssessment(discrepancies=[], consistent_points=["employer Mei Heng Food Pte Ltd matches the payslip issuer"])
    if schema is CreditMatches:
        matches = []
        for line in user.splitlines():
            if line.startswith("- ") and "credit(s) totalling" in line:
                stream = line[2:]
                if "Lee & Partners" in line:
                    matches.append(CreditMatch(credit=stream, document="1000001_sof_letter_1.txt", explanation="Completion account states net proceeds SGD 388,000.00", confidence="high"))
                elif "Mei Heng" in line:
                    matches.append(CreditMatch(credit=stream, document="1000001_payslip_extract_1.txt", explanation="Salary from the employer on record", confidence="medium"))
                else:
                    matches.append(CreditMatch(credit=stream, document=None, explanation="No document on file explains this stream", confidence="high"))
        return CreditMatches(matches=matches)
    if schema is PlausibilityAssessment:
        return PlausibilityAssessment(plausible=True, plausibility_reasons=["salary credits S$3,100 monthly match the employer on record; the S$388,000 credit is sale proceeds per the completion account"],
                                      profile_mismatch=False, expected_behaviour="consistent", expected_behaviour_reasons=["one-off property sale documented on file"],
                                      unresolved_points=[])
    if schema is NarrativeRead:
        return NarrativeRead(signals=[NarrativeSignal(case_id="CM-2025-0003", kind="refusal", quote="Customer stated they would not provide further ownership information")],
                             media=[MediaCategory(hit_id="H-3", category="1", reason="trade finance fraud is financial crime")])
    if schema is ReviewerNotes:
        return ReviewerNotes(missed=[Suggestion(clause="4.7(d)", title="Payslip on file predates the review period by two years",
                                                detail="payslip dated 2023-01-31 against a 2025 review period", evidence="documents 1000001_payslip_extract_1.txt", confidence="medium")],
                             disagreements=[])
    raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture
async def records(bank_api_url):
    async with RecordsClient("inproc", BankApiSettings(url=bank_api_url, api_key=BANK_API_KEY)) as rc:
        yield rc


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(model="fake-model", model_allowlist=("fake-model",), audit_dir=tmp_path / "audit")


def by_clause(pack, clause: str, kind: str | None = None):
    return [f for f in pack.findings if f.clause == clause and (kind is None or f.kind == kind)]


# -- policy ----------------------------------------------------------------------------

def test_policy_tables_and_thresholds_come_from_the_text():
    p = load_policy()
    assert p.baselines["64202"].cash_band == (0.0, 0.02) and "holding" in p.baselines["64202"].industry
    assert p.groups["Singapore"] == 1 and p.groups["Malaysia"] == 2 and p.groups["Myanmar"] == 3
    assert p.groups["Korea, Republic of"] == 1 and p.groups["Korea, Democratic People's Republic of"] == 3
    assert p.group_of("MM") == (3, "Myanmar", True) and p.group_of("VG")[0] == 2 and p.group_of("VG")[2] is False
    assert "200 per cent" in p.clause_text("4.7") and p.title("5.4") == "Plausibility"
    assert p.band(0.91) == "strong" and p.band(0.7) == "possible" and p.band(0.41) == "weak"


# -- an individual with a documented one-off credit ---------------------------------------

async def test_pack_for_an_individual_with_model(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, FakeGateway(fake_model), settings=settings)

    assert pack.in_scope and pack.tier == 2 and not pack.period_inferred
    assert str(pack.period_start) == "2025-01-01" and str(pack.period_end) == "2025-12-31"
    t = pack.transactions
    assert t.credits_total == 3100 * 12 + 388000 and t.declared_turnover == 180000
    assert by_clause(pack, "4.7(b)", "exception"), "credits are 236% of declared"
    assert by_clause(pack, "7.2(a)", "exception"), "the July spike swings the trailing average"
    assert by_clause(pack, "4.7(c)", "condition_met"), "all counterparties are in SG"
    assert by_clause(pack, "7.4(c)", "exception"), "388k in, 380k out within five business days"
    assert by_clause(pack, "7.4(d)", "not_assessed")
    assert by_clause(pack, "8.3", "exception")[0].values["category"] == "sanctions"  # H-2 undispositioned
    assert by_clause(pack, "8.4", "condition_met"), "H-1 eliminated with a DOB mismatch in the weak band"

    assert len(pack.documents) == 2 and {d.doc_type for d in pack.documents} == {"source of funds letter", "payslip extract"}
    sof = next(d for d in pack.documents if d.doc_type == "source of funds letter")
    assert sof.independent is True and sof.age_days is not None
    payslip = next(d for d in pack.documents if d.doc_type == "payslip extract")
    assert payslip.independent is False  # default rule: payslips are not independent
    assert by_clause(pack, "4.7(d)", "condition_met")[0].origin == "model"
    matched = [f for f in pack.findings if f.step == "matching"]
    assert any("Lee & Partners" in f.title and f.kind == "information" for f in matched)
    assert by_clause(pack, "5.4", "condition_met"), "plausibility met"
    assert by_clause(pack, "7.3", "condition_met"), "spike consistent with documented sale"
    suggested = [f for f in pack.findings if f.kind == "model_suggested"]
    assert len(suggested) == 1 and suggested[0].verified is False

    assert [m.step for m in pack.model_calls] == ["documents", "documents", "consistency", "matching", "plausibility", "reviewer"]
    assert all(f.id.startswith("F-") for f in pack.findings) and len({f.id for f in pack.findings}) == len(pack.findings)
    assert all(f.citations for f in pack.findings)
    cond = {c.clause: c.status for c in pack.conditions}
    assert cond["4.3(a)"] == "exception" and cond["4.7(b)"] == "exception" and cond["4.7(c)"] == "met"
    import re
    decision = re.compile(r"should be (rated|closed|confirmed)|I recommend|rate (him|her|them) as|the file can be closed", re.I)
    assert not any(decision.search(f.title) or decision.search(f.detail) for f in pack.findings)

    log = Path(pack.audit_log)
    kinds = [json.loads(l)["event"] for l in log.read_text().splitlines()]
    assert kinds[0] == "pack_start" and kinds[-1] == "pack_end" and kinds.count("model_call") == 6
    md = pack_markdown(pack)
    assert "## Exceptions" in md and "Claude read" in md and "model-suggested" in md


# -- an entity with an ownership mismatch, a refusal and a bad elimination ------------------

async def test_pack_for_an_entity(records, settings):
    pack = await build_pack("PR2026-0002", records, FakeGateway(fake_model), settings=settings)
    assert pack.customer_type == "entity" and pack.tier == 1
    assert any("Corvin Capital" in f.title for f in by_clause(pack, "6.6", "exception")), "shareholder on the extract missing from the record"
    assert any("R. Varga" in f.title for f in by_clause(pack, "6.5(a)", "exception")), "director on the extract missing from officers"
    bad = by_clause(pack, "8.4", "exception")
    assert bad and "strong-band" in bad[0].detail and "no differentiating identifier" in bad[0].detail
    assert by_clause(pack, "4.4(d)", "exception"), "stated refusal read from the narrative"
    assert by_clause(pack, "7.4(a)", "exception"), "Myanmar counterparty is Group 3"
    assert by_clause(pack, "7.4(b)", "exception"), "cash share above the holding-company band"
    assert pack.screening[0].media_category is None  # eliminated hits are not categorised
    cond = {c.clause: c.status for c in pack.conditions}
    assert cond["6.5"] == "exception" and cond["4.4(d)"] == "exception"


# -- code-only run, scope, failures ---------------------------------------------------------

async def test_pack_without_model_runs_the_deterministic_steps_only(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, None, settings=settings, use_model=False)
    assert pack.model is None and pack.model_calls == [] and pack.documents == []
    assert by_clause(pack, "4.7(b)", "exception") and by_clause(pack, "8.3", "exception")
    assert {f.step for f in pack.findings if f.kind == "not_assessed"} >= {"documents", "consistency", "matching", "plausibility"}


async def test_out_of_scope_tier_and_inferred_period(records, settings):
    pack = await build_pack("VGB-PR-2026-0003", records, None, settings=settings, use_model=False)
    assert pack.in_scope is False and "tier 4" in pack.scope_note and pack.period_inferred
    assert by_clause(pack, "4.8.3", "exception"), "open RFI on the customer"


async def test_model_step_failure_is_recorded_and_the_pack_continues(records, settings):
    def flaky(request: ModelRequest):
        if request.output_schema is ConsistencyAssessment:
            raise GatewayError("region unavailable")
        return fake_model(request)

    pack = await build_pack("VGB-PR-2026-0001", records, FakeGateway(flaky), settings=settings)
    assert any(f.step == "consistency" and f.kind == "not_assessed" for f in pack.findings)
    assert "consistency: GatewayError" in pack.not_assessed
    assert [m.step for m in pack.model_calls] == ["documents", "documents", "matching", "plausibility", "reviewer"]


async def test_unknown_review_raises(records, settings):
    with pytest.raises(LoadError):
        await build_pack("VGB-PR-2099-9999", records, None, settings=settings, use_model=False)
