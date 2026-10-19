"""Evidence pack evaluation over the QA sample.

For each QA-sampled review: build the pack (model on), run the check against
the analyst's recorded outcome, and score:

  overturn recall     on the 15 reviews QA overturned, did the pack or the check
                      surface what QA found? (target: miss at most 2)
  false alarms        on the 60 QA concurred with, did the check raise a high or
                      medium flag anyway? (rate, to agree a threshold with Dan)
  citations           every finding carries at least one citation that names a
                      dataset and a record or document (target: 100%)
  faithfulness        Ragas Faithfulness of the model's findings against the
                      documents and record they cite, on a sample per pack
                      (target: 1.0; one invented fact is a defect)

    uv run python -m evals.pack.run [--limit N] [--only overturned|concur|all] [--model M] [--no-ragas]

Needs the stack up (`make up`) and ANTHROPIC_API_KEY. Writes
evals/pack/results/<stamp>/ with report.json and every pack and check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

from kyc_workflow.chat import RecordsClient
from kyc_workflow.config import McpSettings, Settings
from kyc_workflow.gateway import HeliosGateway
from kyc_workflow.workflow import LoadError, build_check, build_pack, load_policy
from kyc_workflow.workflow.steps.documents import record_for_prompt

from evals.pack.cases import load_cases, overturn_surfaced
from evals.ragas_llm import GatewayJudge

warnings.filterwarnings("ignore")
for _name in ("httpx", "httpx2", "ragas", "kyc_workflow.pack", "kyc_workflow.chat"):
    logging.getLogger(_name).setLevel(logging.WARNING)

RESULTS_DIR = Path(__file__).parent / "results"


async def faithfulness_of(pack, records: RecordsClient, metric, max_findings: int) -> list[dict]:
    """Ragas Faithfulness of model-origin findings against what they cite."""
    from ragas.dataset_schema import SingleTurnSample

    out = []
    docs: dict[str, str] = {}
    model_findings = [f for f in pack.findings if f.origin == "model" and f.kind in ("exception", "condition_met", "information")][:max_findings]
    for f in model_findings:
        contexts: list[str] = []
        for c in f.citations:
            if c.document and c.document not in docs:
                r = await records.call("get_document", {"stored_filename": c.document})
                try:
                    docs[c.document] = json.loads(r.text).get("text", "") if not r.is_error else ""
                except ValueError:
                    docs[c.document] = ""
            if c.document and docs.get(c.document):
                contexts.append(docs[c.document])
        if pack.transactions:
            tx = pack.transactions
            contexts.append(f"Transaction profile {tx.period_start} to {tx.period_end}: credits S${tx.credits_total:,.0f} in {tx.credit_count} items, debits S${tx.debits_total:,.0f}, "
                            f"declared turnover {tx.declared_turnover}, ratio {tx.turnover_ratio}, cash share {tx.cash_share}, top counterparties {tx.top_counterparties[:5]}, "
                            f"countries {dict(list(tx.countries.items())[:6])}, monthly credits {[(m.month, round(m.credits)) for m in tx.months]}")
        contexts.append("Customer record: " + json.dumps({k: v for k, v in pack.model_dump().items() if k in ("customer_ref", "customer_name", "customer_type", "tier")}))
        sample = SingleTurnSample(user_input=f"What does the file show for §{f.clause}?", response=f"{f.title}. {f.detail}", retrieved_contexts=contexts)
        try:
            score = float(await metric.single_turn_ascore(sample))
        except Exception as err:  # the judge failing is recorded, not fatal
            score = None
            out.append({"finding": f.id, "clause": f.clause, "score": None, "error": type(err).__name__})
            continue
        out.append({"finding": f.id, "clause": f.clause, "score": score})
    return out


async def run(limit: int | None, only: str, model: str | None, judge_model: str | None, use_ragas: bool, mcp: str | None,
              max_faith: int) -> int:
    from kyc_workflow.gateway import AnthropicBackend

    settings = Settings.from_env()
    model = model or settings.eval_model
    judge_model = judge_model or settings.eval_model
    settings = settings.with_model(judge_model).with_model(model)
    gateway = HeliosGateway(AnthropicBackend(), settings)
    policy = load_policy()
    metric = None
    judge = GatewayJudge(gateway, judge_model)
    if use_ragas:
        from ragas.metrics import Faithfulness

        metric = Faithfulness(llm=judge)

    cases = load_cases()
    if only == "overturned":
        cases = [c for c in cases if not c.concurs]
    elif only == "concur":
        cases = [c for c in cases if c.concurs]
    if limit:
        cases = cases[:limit]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RESULTS_DIR / stamp
    (out_dir / "packs").mkdir(parents=True, exist_ok=True)
    results = []
    started = time.monotonic()
    try:
        async with RecordsClient(mcp) as records:
            print(f"pack model {model}  |  judge {judge_model if use_ragas else 'off'}  |  mcp {records.target}  |  {len(cases)} reviews\n")
            for case in cases:
                t0 = time.monotonic()
                row = {"review_id": case.review_id, "kind": case.kind, "recorded_outcome": case.recorded_outcome, "qa_outcome": case.qa_outcome}
                try:
                    pack = await build_pack(case.review_id, records, gateway, settings=settings, policy=policy, model=model,
                                            analyst_id="EVAL", audit_dir=out_dir / "audit")
                except LoadError as err:
                    row.update(status="not_loadable", error=str(err)[:200])
                    results.append(row)
                    print(f"skip {case.review_id:<20} {case.kind:<18} not loadable: {str(err)[:80]}")
                    continue
                outcome = pack.recorded_outcome or case.recorded_outcome
                report = await build_check(pack, gateway, settings=settings, recorded_outcome=outcome, model=model,
                                           analyst_id="EVAL", audit_dir=out_dir / "audit")
                (out_dir / "packs" / f"{case.review_id}.json").write_text(pack.model_dump_json(indent=2))
                (out_dir / "packs" / f"{case.review_id}.check.json").write_text(report.model_dump_json(indent=2))
                exc = {f.clause for f in pack.findings if f.kind == "exception"}
                flags = {f.code for f in report.flags}
                surfaced = overturn_surfaced(case, exc, flags)
                cited = sum(1 for f in pack.findings if any(c.dataset and (c.record_id or c.document) for c in f.citations))
                faith = await faithfulness_of(pack, records, metric, max_faith) if metric else []
                scores = [x["score"] for x in faith if x.get("score") is not None]
                row.update(status="ok", tier=pack.tier, in_scope=pack.in_scope, period_inferred=pack.period_inferred,
                           findings=len(pack.findings), exceptions=sorted(exc), model_suggested=sum(1 for f in pack.findings if f.kind == "model_suggested"),
                           check_flags=sorted(flags), check_clean=report.clean, surfaced=surfaced,
                           false_alarm=(case.concurs and not report.clean), citations_ok=cited, citations_total=len(pack.findings),
                           faithfulness=faith, faithfulness_mean=(sum(scores) / len(scores)) if scores else None,
                           model_calls=len(pack.model_calls) + len(report.model_calls),
                           input_tokens=sum(m.input_tokens for m in pack.model_calls + report.model_calls),
                           output_tokens=sum(m.output_tokens for m in pack.model_calls + report.model_calls),
                           seconds=round(time.monotonic() - t0, 1))
                results.append(row)
                mark = "ok  " if (surfaced is None and not row["false_alarm"]) or surfaced else ("FA  " if row["false_alarm"] else "MISS")
                print(f"{mark} {case.review_id:<20} {case.kind:<18} tier={pack.tier} exceptions={len(exc)} flags={len(flags)} "
                      f"faith={row['faithfulness_mean'] if row['faithfulness_mean'] is not None else '-'} {row['seconds']}s")
    except Exception as err:
        if not results:
            print(f"cannot run: {type(err).__name__}: {err}. Is the stack up ({mcp or McpSettings.from_env().url})? Run `make up` first.", file=sys.stderr)
            return 2
        raise

    ok = [r for r in results if r.get("status") == "ok"]
    overturned = [r for r in ok if r["surfaced"] is not None]
    recalled = sum(1 for r in overturned if r["surfaced"])
    concur = [r for r in ok if r["kind"] == "concur"]
    false_alarms = sum(1 for r in concur if r["false_alarm"])
    cit_ok = sum(r["citations_ok"] for r in ok)
    cit_total = sum(r["citations_total"] for r in ok)
    faith_scores = [x["score"] for r in ok for x in r["faithfulness"] if x.get("score") is not None]
    summary = {
        "model": model, "judge": judge.summary() if use_ragas else None, "reviews": len(results), "built": len(ok),
        "overturned_scored": len(overturned), "overturn_recall": (recalled / len(overturned)) if overturned else None, "recalled": recalled,
        "concur_scored": len(concur), "false_alarms": false_alarms, "false_alarm_rate": (false_alarms / len(concur)) if concur else None,
        "citation_rate": (cit_ok / cit_total) if cit_total else None,
        "faithfulness_mean": (sum(faith_scores) / len(faith_scores)) if faith_scores else None, "faithfulness_samples": len(faith_scores),
        "input_tokens": sum(r.get("input_tokens", 0) for r in ok), "output_tokens": sum(r.get("output_tokens", 0) for r in ok),
        "seconds": round(time.monotonic() - started, 1),
    }
    # the UI reads these two like the other evals
    summary["pass_rate"] = summary["overturn_recall"] if summary["overturn_recall"] is not None else (1 - summary["false_alarm_rate"] if summary["false_alarm_rate"] is not None else 0)
    summary["passed"] = recalled if overturned else len(concur) - false_alarms
    summary["total"] = len(overturned) if overturned else len(concur)
    print(f"\nbuilt {len(ok)}/{len(results)} packs in {summary['seconds']}s; overturn recall {recalled}/{len(overturned)}; "
          f"false alarms {false_alarms}/{len(concur)}; citations {cit_ok}/{cit_total}; "
          f"faithfulness {summary['faithfulness_mean'] if summary['faithfulness_mean'] is not None else '-'} over {len(faith_scores)} findings; "
          f"tokens in={summary['input_tokens']} out={summary['output_tokens']}")
    (out_dir / "report.json").write_text(json.dumps({**summary, "cases": results}, indent=2, default=str))
    print(f"written {out_dir.relative_to(Path.cwd()) if out_dir.is_relative_to(Path.cwd()) else out_dir}/report.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", choices=("overturned", "concur", "all"), default="all")
    parser.add_argument("--model", default=None, help="pack model (default KYC_EVAL_MODEL)")
    parser.add_argument("--judge-model", default=None, help="Ragas judge (default KYC_EVAL_MODEL)")
    parser.add_argument("--no-ragas", action="store_true", help="skip Faithfulness scoring")
    parser.add_argument("--max-faith", type=int, default=3, help="model findings per pack to score for faithfulness")
    parser.add_argument("--mcp", default=None)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.limit, args.only, args.model, args.judge_model, not args.no_ragas, args.mcp, args.max_faith))


if __name__ == "__main__":
    sys.exit(main())
