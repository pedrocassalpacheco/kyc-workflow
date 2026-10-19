"""The pre-submit check over packs built from the fixture export with the fake model."""

import pytest

from kyc_workflow.chat import RecordsClient
from kyc_workflow.config import BankApiSettings, Settings
from kyc_workflow.gateway import FakeGateway
from kyc_workflow.workflow import build_check, build_pack, check, check_markdown
from kyc_workflow.workflow.check import RationaleCheck, Statement
from tests.conftest import BANK_API_KEY
from tests.test_workflow import fake_model

pytestmark = pytest.mark.anyio


@pytest.fixture
async def records(bank_api_url):
    async with RecordsClient("inproc", BankApiSettings(url=bank_api_url, api_key=BANK_API_KEY)) as rc:
        yield rc


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(model="fake-model", model_allowlist=("fake-model",), audit_dir=tmp_path / "audit")


def codes(report) -> set[str]:
    return {f.code for f in report.flags}


async def test_confirming_over_an_unresolved_hit_and_a_cross_check_exception(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, FakeGateway(fake_model), settings=settings)
    assert pack.recorded_outcome == "unchanged" and pack.recorded_clauses == ["5.4", "6.6"]
    report = check(pack, "unchanged", ["4.3"], "Rating confirmed, nothing of note.", None)
    assert {"CONFIRMED_OVER_UNRESOLVED_HIT", "ESCALATION_TRIGGER_IGNORED", "CLAUSE_CONTRADICTED"} <= codes(report)
    assert not report.clean
    md = check_markdown(report)
    assert "CONFIRMED_OVER_UNRESOLVED_HIT" in md and "flag(s)" in md


async def test_no_clause_and_thin_rationale(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, None, settings=settings, use_model=False)
    report = check(pack, "request_info", [], "ok", None)
    assert {"NO_CLAUSE", "THIN_RATIONALE"} <= codes(report)


async def test_rfi_without_trigger_and_escalation_without_trigger(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, None, settings=settings, use_model=False)
    # strip the pack of exceptions to simulate a clean file
    pack.findings = [f for f in pack.findings if f.kind != "exception"]
    pack.conditions = []
    assert "RFI_WITHOUT_TRIGGER" in codes(check(pack, "request_info", ["4.5(a)"], "x" * 50, None))
    assert "ESCALATION_WITHOUT_TRIGGER" in codes(check(pack, "escalate", ["4.4(c)"], "x" * 50, None))
    assert check(pack, "unchanged", ["4.3"], "Credits consistent with salary; no hits; rating confirmed under 4.3.", None).clean


async def test_outcome_vocabulary(records, settings):
    pack = await build_pack("VGB-PR-2026-0001", records, None, settings=settings, use_model=False)
    assert "NO_OUTCOME" in codes(check(pack, "", ["4.3"], "x" * 50, None))
    assert "UNKNOWN_OUTCOME" in codes(check(pack, "approved", ["4.3"], "x" * 50, None))


async def test_ownership_change_and_customer_supplied_only(records, settings):
    pack = await build_pack("PR2026-0002", records, FakeGateway(fake_model), settings=settings)
    report = check(pack, "unchanged", ["4.3"], "Stable business activity, no anomalies noted.", None)
    assert "OWNERSHIP_CHANGE_UNADDRESSED" in codes(report)
    assert "ESCALATION_TRIGGER_IGNORED" in codes(report)  # the refusal and the 8.4 breach


async def test_rationale_is_read_by_the_model_through_build_check(records, settings):
    def model(request):
        if request.output_schema is RationaleCheck:
            return RationaleCheck(statements=[
                Statement(text="Credits matched to completion account", supported=True, basis="F-matching"),
                Statement(text="registry extract pulled", supported=False, basis="no registry extract on file for an individual"),
            ])
        return fake_model(request)

    pack = await build_pack("VGB-PR-2026-0001", records, FakeGateway(model), settings=settings)
    report = await build_check(pack, FakeGateway(model), settings=settings)
    assert report.recorded_outcome == "unchanged" and report.rationale_faithfulness == 0.5
    assert len(report.unsupported_statements) == 1 and "RATIONALE_UNSUPPORTED" in codes(report)
    assert report.model_calls and report.model_calls[0].step == "check"


def test_qa_case_kinds_and_scoring():
    from evals.pack.cases import QACase, load_cases, overturn_surfaced

    cases = load_cases()
    assert len(cases) == 75 and sum(1 for c in cases if not c.concurs) == 15
    kinds = {c.kind for c in cases if not c.concurs}
    assert kinds == {"needed_rfi", "needed_escalation", "over_asked", "over_escalated"}
    rfi = next(c for c in cases if c.kind == "needed_rfi")
    assert overturn_surfaced(rfi, {"4.7(b)"}, set()) is True and overturn_surfaced(rfi, set(), set()) is False
    esc = next(c for c in cases if c.kind == "needed_escalation")
    assert overturn_surfaced(esc, {"8.3"}, set()) is True
    assert overturn_surfaced(next(c for c in cases if c.kind == "over_asked"), set(), {"RFI_WITHOUT_TRIGGER"}) is True
    assert overturn_surfaced(QACase("x", "unchanged", "unchanged", True, ""), set(), set()) is None
