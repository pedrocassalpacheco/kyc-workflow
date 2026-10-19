"""Routing evaluation: given an analyst-style request, does a model pick the
right vgb-records tool with the right arguments? Scored with Ragas
ToolCallAccuracy against hand-written reference calls.

This is outside the workflow design: the harness routes in code and the
model never chooses a tool (CLAUDE.md, "Architecture"). The eval exists to
show that the tool descriptions are good enough that a model would route
correctly if it were allowed to, which is also a proxy for whether a person
reading them would. Model calls go through HeliosGateway like every other
model call in this project.

    uv run python -m evals.routing.run [--model M] [--threshold 0.9] [--mcp URL]

The model defaults to KYC_EVAL_MODEL from .env.

Tool definitions come from the running vgb-records MCP server (`make up`,
MCP_URL); nothing about the tools is written down here. Needs
ANTHROPIC_API_KEY in .env. Writes a JSON record of every run to
evals/routing/results/ (gitignored) and exits non-zero below the threshold.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kyc_workflow.chat.mcp_client import RecordsClient
from kyc_workflow.config import McpSettings, Settings
from kyc_workflow.gateway import HeliosGateway, ModelGateway, ModelRequest, ToolDef

from evals.routing.cases import CASES

warnings.filterwarnings("ignore")  # ragas and langchain are noisy on import
for _name in ("httpx", "httpx2"):  # the SDK logs every request at INFO once ragas configures logging
    logging.getLogger(_name).setLevel(logging.WARNING)

RESULTS_DIR = Path(__file__).parent / "results"


# -- tool definitions from the MCP server ---------------------------------------

async def _fetch_tools(target: str | None) -> tuple[str, list[ToolDef]]:
    async with RecordsClient(target) as records:
        return records.instructions, records.tools


def load_tools(target: str | None = None) -> tuple[str, list[ToolDef]]:
    """Server instructions and tool definitions, as the MCP server advertises
    them. Descriptions are passed through untouched: they are what is being
    evaluated. `target` is the server URL (default MCP_URL) or "inproc" for tests."""
    return asyncio.run(_fetch_tools(target))


# -- scoring -------------------------------------------------------------------

def score_case(case: dict, predicted: list[dict[str, Any]]) -> float:
    """Ragas ToolCallAccuracy for one case: 1.0 when the predicted calls match
    the reference names in sequence and every reference argument matches
    exactly; 0.0 when the tool is wrong; partial for partly right arguments.
    Extra predicted arguments are ignored; a missing reference argument costs
    its share."""
    from ragas.dataset_schema import MultiTurnSample
    from ragas.messages import AIMessage, HumanMessage, ToolCall
    from ragas.metrics import ToolCallAccuracy

    sample = MultiTurnSample(
        user_input=[
            HumanMessage(content=case["prompt"]),
            AIMessage(content="", tool_calls=[ToolCall(name=p["name"], args=p["args"]) for p in predicted]),
        ],
        reference_tool_calls=[ToolCall(name=e["name"], args=e["args"]) for e in case["expected"]],
    )
    metric = ToolCallAccuracy(strict_order=case.get("ordered", True))
    return float(asyncio.run(metric.multi_turn_ascore(sample)))


# -- asking the model ----------------------------------------------------------

def ask_model(gateway: ModelGateway, model: str, instructions: str, tools: list[ToolDef], prompt: str) -> list[dict[str, Any]]:
    """One turn through the gateway: the model sees the server's instructions and
    tools and the analyst's request. Returns the tool calls it made (possibly none)."""
    response = gateway.complete(ModelRequest(
        case_id="EVAL-ROUTING",
        analyst_id="EVAL",
        model=model,
        max_tokens=1024,
        system=(
            "You are assisting a KYC analyst at Veridian Global Bank. You have the "
            "tools of the vgb-records server. Call the tool that answers the request, "
            "with arguments taken from the request. If no tool can answer it, call "
            "nothing and say so.\n\n" + instructions
        ),
        tools=tools,
        user=prompt,
    ))
    return [{"name": c.name, "args": dict(c.input)} for c in response.tool_calls]


def run(model: str | None, threshold: float, case_ids: list[str] | None = None, mcp: str | None = None) -> int:
    from kyc_workflow.gateway import AnthropicBackend

    settings = Settings.from_env()
    model = model or settings.eval_model
    settings = settings.with_model(model)
    gateway = HeliosGateway(AnthropicBackend(), settings)
    try:
        instructions, tools = load_tools(mcp)
    except Exception as err:
        print(f"cannot reach the MCP server at {mcp or McpSettings.from_env().url}: {type(err).__name__}. "
              "Run `make up` first.", file=sys.stderr)
        return 2
    print(f"{len(tools)} tools from {mcp or McpSettings.from_env().url}")
    cases = [c for c in CASES if not case_ids or c["id"] in case_ids]

    rows = []
    for case in cases:
        predicted = ask_model(gateway, model, instructions, tools, case["prompt"])
        score = score_case(case, predicted)
        rows.append({"id": case["id"], "prompt": case["prompt"], "expected": case["expected"],
                     "predicted": predicted, "score": score})
        mark = "ok " if score == 1.0 else "FAIL" if score == 0.0 else "part"
        got = ", ".join(f"{p['name']}({', '.join(f'{k}={v!r}' for k, v in p['args'].items())})" for p in predicted) or "(no call)"
        print(f"{mark} {score:.2f}  {case['id']:<22} -> {got}")

    mean = sum(r["score"] for r in rows) / len(rows) if rows else 0.0
    perfect = sum(1 for r in rows if r["score"] == 1.0)
    print(f"\nmodel {model}: {perfect}/{len(rows)} cases exact, mean tool-call accuracy {mean:.3f} (threshold {threshold})")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"{stamp}_{model}.json"
    out.write_text(json.dumps({"model": model, "threshold": threshold, "mean": mean,
                               "exact": perfect, "cases": rows}, indent=2))
    print(f"written {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0 if mean >= threshold else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=None, help="model to evaluate (default KYC_EVAL_MODEL from .env)")
    parser.add_argument("--threshold", type=float, default=0.9, help="minimum mean score to pass")
    parser.add_argument("--case", action="append", dest="case_ids", help="run only this case id (repeatable)")
    parser.add_argument("--mcp", default=None, help="MCP server URL (default MCP_URL)")
    args = parser.parse_args(argv)
    return run(args.model, args.threshold, args.case_ids, args.mcp)


if __name__ == "__main__":
    sys.exit(main())
