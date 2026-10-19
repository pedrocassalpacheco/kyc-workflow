# VGB KYC review workflow: prototype

Prototype of an AI-supported workflow that prepares low and medium risk periodic
KYC reviews for Veridian Global Bank (VGB) analysts. Read
`docs/poc-proposal.md` for what we are building and why, and
`docs/gap-report.md` for the discovery detail behind each constraint.
`docs/glossary.txt` defines the bank's terms (Castellan, Helios, MCP server,
RFI, ACRA, POL-042, C1/C2).

This file holds the rules that must hold on every change. When the proposal and
this file disagree, this file wins for code and the proposal wins for scope.

## What it produces

Two documents per review. Build them in this order:

1. **Evidence pack** (build first). Prepared before the analyst opens the file.
   What changed since the last review; each material credit matched to the
   document that explains it, with the document date, its age against the
   90-day rule and whether it is independent of the customer; new screening
   hits next to their previous dispositions; ownership on the customer record
   compared with the registry extract on file; the POL-042 clauses the evidence
   points to, each linked to the evidence.
2. **Check report**. Run on the analyst's recorded outcome, clauses and
   rationale against the pack. Flags: no clause named, outcome confirmed over an
   unresolved hit or an open RFI, escalation or RFI triggers ignored, an RFI or
   escalation with no trigger in the file, a cited clause the pack contradicts,
   expired or customer-supplied evidence, ownership change unaddressed, and
   rationale statements the pack does not support.

Both exist in `src/kyc_workflow/workflow/` (`build_pack`, `build_check`); the
UI's Workflow view and `make pack` run them. Treat the evaluation in
`evals/pack/` as the gate for any change to either.

## Non-negotiables (the control boundary)

These are invariants. Write tests that assert them.

- The workflow **never** outputs a risk rating or a recommendation to change one.
- The workflow **never** writes rationale or narrative text for the analyst.
- The workflow **never** closes, submits, marks or writes to a case. All sources
  are read-only.
- **Every statement in the pack carries a citation**: source system, document
  id, document date, and the location (page or field) it came from. A statement
  that cannot be traced to a source is a defect, not a statistic. Prefer "not
  found in file" over a guess.
- The workflow records what it read and what it concluded, per case, in a local
  audit log inside the project. Nothing about prompts or responses is logged
  anywhere else.
- Analyst id and case id travel with every model call as metadata, never as a
  permission boundary.

## Architecture: a fixed workflow, not an agent

A periodic review follows the same steps every time, so the steps are fixed in
code and Claude is called inside them for reading and comparing. Claude does
not choose its own path, call sources on its own initiative, or decide when a
review is done. No agent loop, no multi-agent, no tool search.

Step sequence for the evidence pack:

1. `load_case`: pull the case, prior review, documents, screening, transactions
   and customer record from the five sources.
2. `detect_changes`: diff the customer record against the prior review pack.
3. `extract_documents`: for each document, pull date, parties, amounts and type
   (Claude, with citations).
4. `match_credits`: match each material credit to the document that explains it
   (Claude, with citations); compute document age and independence (code).
5. `screening_diff`: new hits vs carried-forward hits, with prior dispositions
   (code).
6. `compare_ownership`: customer record vs registry extract on file; flag
   mismatches, unscreened parties and stale extracts (code, Claude only for
   reading the extract).
7. `map_clauses`: suggest POL-042 clauses from the findings, each linked to the
   evidence that triggered it (code table first, Claude only where the table
   is ambiguous).
8. `render_pack`: produce the evidence pack as structured data plus a Markdown
   rendering.

Deterministic checks (date arithmetic, set differences, threshold tests) are
code, never the model. The model reads and compares; it does not calculate.

## Model access: always through the gateway abstraction

Production at the bank calls Claude only through **Helios**, the bank's gateway
to Vertex AI in Singapore. Nothing calls a model provider directly. The
prototype must respect that shape so nothing has to be rewritten later.

- Define a `ModelGateway` protocol in `src/kyc_workflow/gateway/`. All model
  calls in the workflow go through it. No module outside `gateway/` imports the
  Anthropic SDK.
- `HeliosGateway` simulates Helios: it accepts a request with `caller_id`,
  `case_id` and `analyst_id`, logs metadata only (caller, timestamp, model,
  token counts, latency, request id) and never content, applies no redaction and
  no guardrails, is pinned to one region with no failover (fail, then retry),
  and rejects features Helios does not offer (embeddings, batch). Tool use is
  passed through: Helios today has only the Gemini path's older tool schema,
  and the working assumption is that approving Claude behind Helios brings
  Claude's tool use with it. Internally it delegates to a backend.
- `AnthropicBackend` is the only place the Anthropic SDK is used. It reads
  `ANTHROPIC_API_KEY` from `.env`. Use the Messages API with structured outputs
  for anything the code consumes.
- Default model is `claude-sonnet-4-6`, the newest Claude served from the
  Singapore regional endpoint on Vertex. Keep it in config, not in code, so the
  bank's model string can be swapped in. Do not tune prompts against a model the
  bank cannot run.
- Prompt caching: put the policy text and instructions first and stable, the
  case material last.

## Data sources: one MCP server over the bank's HTTP API

The bank's data pack is unzipped in `data/` and served by the bank's own
reference HTTP API in `bank_api/server.py`, used as delivered. On top of it
sits one MCP server, `vgb-records`, in `src/kyc_workflow/mcp_server/`, with
read-only tools grouped by Ben's five record systems (customer master,
screening, case history, document store, transaction summary). Every tool is
a thin call to the HTTP API; the server never bypasses it, never writes, and
never exposes `qa_sample.csv`, which is evaluation ground truth.

- Tool descriptions state the record system, when to use the tool, inputs and
  outputs, and what it does not do. The harness picks tools in code, through
  an MCP client; the model never chooses a tool.
- Every result carries a `source` block (system, dataset, request ids) so a
  statement can cite where it came from.
- Lookups try every identifier shape in the export and report the match.
- Tests run the real HTTP server over the synthetic export in
  `tests/fixtures/bank_export/` and drive the MCP server in memory.

- Seed cases, built from the interview transcripts in `docs/interviews/`:
  `PR-88214` (payslips only, pasted rationale, no clause: overturned),
  `PR-88301` (stale employer letter, open commission RFI, unscreened family
  company, 2023 registry extract), `VGB-C-088410` (registry contradicts customer
  record on a 30% shareholder, unscreened new director, payment to the
  unrecorded shareholder: overturned), and Madam Tan's clean medium from Nora's
  walkthrough.
- All fixture data is synthetic. Never put real customer data in this repo.
- The masked customer view may drop names and related-party fields. Fixtures
  carry a `masked` variant so the ownership step can be tested both ways.

## Policy

POL-042 v4.2 is in the repo at `docs/risk-rating-policy-v4.2.md` (the same
file the data pack carries); read the clause text from there, do not
paraphrase it into code. `data/` itself is not committed. Two rules are
unsettled with Compliance and must stay configurable, with the default
flagged in the pack output:

- the 90-day document validity window (Nora applies it, QA's checklist does
  not name it);
- whether a payslip counts as independent evidence (QA says yes, Nora and the
  PR-88214 overturn say no). Default: not independent.

## Evaluation: Ragas is the framework

`evals/` holds the evaluation set and runner. Ragas (already a dependency) is
the framework; do not add another. Grade with the Ragas metrics for
faithfulness and citation/context precision against the fixture documents,
plus custom checks for the invariants above.

The evidence pack is good enough only if, on the evaluation set:

- every statement traces to a fixture document (faithfulness = 1.0; one
  invented fact fails the run);
- the recorded reason for overturn is surfaced on at least 18 of the 20
  overturned cases;
- no pack contains a rating, a recommendation or narrative text;
- clean cases raise no false alarms beyond an agreed threshold.

Evaluation set: the bank's QA sample (`data/qa_sample.csv`, 60 concurred and
15 overturned, with reasons) is the ground truth and is never served by the
MCP server; constructed cases for rare situations and for attempts to make
the workflow rate, close or write live in fixture exports under `evals/`.
Never let a constructed case in without a hand-written expected outcome.

## Conventions

- Python 3.13, `uv` for everything (`uv add`, `uv run`). Do not use pip.
- Layout: `src/kyc_workflow/{gateway,mcp_server,chat,ui,workflow,models,policy,audit}`,
  `cases/`, `evals/`, `tests/`. `main.py` is a thin CLI:
  `uv run main.py pack <case_id>`.
- Pydantic models for every input and output shape. The pack is structured data
  first; Markdown is a rendering of it.
- Tests with pytest. Unit tests for every deterministic step run without a
  model. Model-backed steps get a `FakeGateway` with canned responses so the
  suite runs offline.
- Commit messages say what changed and why. Never commit `.env`, `audit/` or
  `output/`.

## Out of scope for this prototype

High-risk files, drafted rationale text, write-back to Castellan, fresh
registry pulls, per-analyst access control, failover across regions, and any
agentic loop. If a change needs one of these, stop and raise it instead.
