"""One live call through HeliosGateway -> AnthropicBackend -> Claude.

Runs only with `pytest -m integration` and needs ANTHROPIC_API_KEY in .env.
Uses KYC_EVAL_MODEL from .env, a small model, to keep the cost of a test run
negligible.
"""

import os

import pytest
from pydantic import BaseModel, Field

from kyc_workflow.config import Settings, load_env
from kyc_workflow.gateway import HeliosGateway, ModelRequest

pytestmark = pytest.mark.integration

class DocumentDate(BaseModel):
    document_date: str = Field(description="Date the document is dated, as an ISO date YYYY-MM-DD")
    issuer: str = Field(description="Organisation that issued the document, as written")


@pytest.fixture(scope="module")
def live_gateway(tmp_path_factory):
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set; put it in kyc-workflow/.env")
    from kyc_workflow.gateway import AnthropicBackend

    settings = Settings.from_env()
    settings = settings.with_model(settings.eval_model)
    return HeliosGateway(
        AnthropicBackend(),
        settings,
        log_path=tmp_path_factory.mktemp("audit") / "helios.jsonl",
    )


def test_structured_extraction_round_trip(live_gateway):
    resp = live_gateway.complete(ModelRequest(
        case_id="PR-TEST-0001",
        analyst_id="AN-TEST",
        system=(
            "You extract fields from bank documents. Answer only with the fields "
            "requested. If a field is not in the document, use an empty string."
        ),
        user=(
            "Document:\n"
            "MEADOWVALE COLD STORAGE LOGISTICS PTE. LTD.\n"
            "EMPLOYMENT CONFIRMATION LETTER\n"
            "Dated: 24 July 2026\n"
            "We confirm that the above-named has been employed by us since 2019.\n"
        ),
        output_schema=DocumentDate,
        max_tokens=256,
    ))

    assert resp.model.startswith(live_gateway.settings.eval_model)
    assert isinstance(resp.parsed, DocumentDate)
    assert resp.parsed.document_date == "2026-07-24"
    assert "meadowvale" in resp.parsed.issuer.lower()
    assert resp.usage.input_tokens > 0 and resp.usage.output_tokens > 0

    entry = live_gateway.entries[-1]
    assert entry.status == "ok"
    assert entry.case_id == "PR-TEST-0001" and entry.analyst_id == "AN-TEST"
    assert entry.input_tokens == resp.usage.input_tokens
