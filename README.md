# VGB KYC review workflow

An AI-supported workflow for Veridian Global Bank's periodic KYC reviews. It
prepares the evidence for a low or medium risk review before an analyst
opens the file and checks the analyst's recorded outcome before it is
submitted, so analysts spend their time deciding and signing instead of
assembling files, and every closed file names the policy clause it relied on.

This repository holds the proof of concept built against the bank's data
pack. It runs on a laptop with one API key.

- **What was proposed**: `docs/plan.md` (the seven-point plan sent to the
  bank), `docs/poc-proposal.md` (the longer proposal), `docs/gap-report.md`
  (discovery findings), `docs/interviews/` (the transcripts behind them),
  `docs/glossary.txt` (the bank's terms).
- **Design rules for any change**: `CLAUDE.md`.
- **This file**: what was built, how it differs from the plan, and how to run it.

---

## 1. Quick start

### Requirements

| What | Why | How to get it |
|---|---|---|
| Python 3.13 | the project targets it; `.python-version` pins it | uv installs it for you on first `uv sync` if it is missing |
| [uv](https://docs.astral.sh/uv/) | installs dependencies from `uv.lock` and runs every command; pip is not used | macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`; or `brew install uv` |
| GNU make | every entry point is a make target | macOS: ships with Xcode command line tools (`xcode-select --install`); Linux: `apt install make` |
| curl, python3 on PATH | `make status` and `make up` use them to probe the services | present on macOS and most Linux installs |
| an Anthropic API key | anything that calls the model: packs, chat, evals, the live test | put it in `.env` as `ANTHROPIC_API_KEY`; the offline tests and the data services run without one |
| ports 8000, 8001, 8002 free | the bank API, the MCP server and the UI | change with `VGB_PORT`, `MCP_PORT`, `UI_PORT` in `.env` or on the make command line |


### Steps

```bash
git clone <this repo> && cd kyc-workflow
uv sync                                   # installs everything from uv.lock
cp .env.example .env                      # then put your ANTHROPIC_API_KEY in .env
make test                                 # 152 offline tests, no key needed
make up                                   # bank API :8000, MCP server :8001, UI :8002
open http://127.0.0.1:8002                # the UI
make pack REVIEW=VGB-PR-2026-1173         # an evidence pack in the terminal
make chat                                 # chat over the records in the terminal
make down
```

`make` with no target lists every target. `make status` tells you whether
the three services answer. `make restart` after changing server code.

The bank's data pack is already unzipped in `data/` (13 CSV files, 1,032
document texts, the review worklist, POL-042 v4.2). It is synthetic; nothing
in it is real customer data.

## 2. What the bank asked for and what was promised

The MAS inspection found about 47,000 overdue periodic reviews and, in 17 of
60 sampled files, a conclusion recorded without naming the policy clause
relied on. The plan in `docs/plan.md` promised:

1. **An evidence pack** before the analyst opens a low or medium review:
   read-only, every statement cited to a source document or record.
2. **A pre-submit check** of the analyst's finished work: missing clauses,
   stale or customer-supplied documents, unaddressed screening hits,
   ownership changes without a registry extract, open RFIs. A clean check
   report as the condition of the checker accepting the file.
3. **Not an agent**: steps fixed in code, the model used inside them only to
   read and compare. Never a rating, never a recommendation, never a closure,
   never rationale text written for the analyst.
4. **Through the bank's gateway**: every model call via Helios to Claude on
   Vertex in Singapore; metadata-only logging at the gateway; the bank's
   five MCP servers as the only data path; nothing written back to Castellan.
5. **Judged by QA's number**: the overturn rate on tool-assisted files at or
   below today's, on an evaluation set of 60 closed reviews, with the
   recorded overturn reason surfaced on at least 18 of 20 overturned files
   and no statement in a pack that cannot be traced to a document.
6. **Handover to the bank**: runbooks and monitoring for Ben's platform team,
   a clause-to-situation guide for the floor, the evaluation set and the
   cost figures.

## 3. What was built

Everything below is in this folder and runs with `make up`.

```
                    ┌────────────────────────────────────────────────────────┐
  browser ──────────┤  UI  (Starlette, one page, SSE)  :8002                 │
  terminal ─────────┤  CLI main.py: pack | chat | ping                       │
                    └───────┬───────────────────────────────┬────────────────┘
                            │                               │
             ┌──────────────▼──────────────┐   ┌────────────▼─────────────┐
             │ workflow/  build_pack       │   │ chat/  ChatSession       │
             │  12 fixed steps, 6 w/ Claude│   │  guardrails, audit log   │
             │ build_check                 │   │                          │
             └──────┬──────────────┬───────┘   └──────┬───────────┬───────┘
                    │              │                  │           │
         ┌──────────▼───────┐   ┌──▼──────────────────▼──┐   ┌────▼────────────┐
         │ gateway/         │   │ mcp_server/  vgb-records│   │ evals/ (Ragas)  │
         │ HeliosGateway    │   │ 15 read-only tools     │   │ routing         │
         │ AnthropicBackend │   │ over the bank's API    │   │ guardrails      │
         │ metadata log     │   └──────────┬─────────────┘   │ pack            │
         └────────┬─────────┘              │                 └─────────────────┘
                  │                ┌───────▼────────┐
            Claude (API)           │ bank_api/      │  the bank's own starter, as delivered
                                   │ HTTP over data/│  :8000
                                   └────────────────┘
```

### 3.1 The evidence pack (`src/kyc_workflow/workflow/`)

`build_pack(review_id)` runs twelve steps in a fixed order. Code does the
counting; Claude reads and compares inside six of them; nothing decides.

| Phase | Step | Who | What it does and which clause |
|---|---|---|---|
| Load | load_case | code | the review row from the worklist, customer record, accounts, owners, officers, screening hits, prior cases and write-ups, documents on file, transactions over the review period. All through the MCP server, every record keeping the bank's request id (§4.1, §9.1) |
| Count | transactions | code | credits against declared turnover with the 200% tolerance (§4.7(b)); monthly swings beyond ±40% for three months (§7.2(a)); counterparties outside declared markets (§7.2(b), §4.7(c)); Group 3 jurisdictions (§7.4(a)); cash share against the Appendix B band (§7.4(b)); pass-through within five business days (§7.4(c)); structuring reported as not assessable, no threshold in the policy (§7.4(d)) |
| Count | screening | code | score bands (§8.2); undispositioned hits (§8.3); eliminations in the strong band, of sanctions results, or without an identifier (§8.4); true matches (§4.4(a), (b), §8.5); owners with no screening on file (§6.5(b)) |
| Count | history | code | open RFIs on a file about to close (§4.8.3); repeated RFIs (§4.4(d)); prior review outcomes and alerts |
| Read | documents | Claude | each document into issuer, date, subject, amounts, facts, shareholders and directors, customer-supplied or not. Code then computes age against sign-off and independence under the two unsettled rules (§5.4) |
| Compare | consistency | Claude | each document's substance against the record: administrative or aged differences (§4.5(c)), substantive ones (§4.4(e)), agreement (§4.7(d)) |
| Compare | ownership | code over Claude's read | shareholders and directors on the registry extract against the owners and officers on record (§6.5(a), §6.6) |
| Compare | matching | Claude | each stream of credits, by counterparty, to the document that explains it (§5.4) |
| Compare | plausibility | Claude | activity against the declared employment, business, source of funds and the Appendix B baseline (§5.4, §7.3, §7.5) |
| Compare | narratives | Claude | refusals and lapsed RFIs in case narratives (§4.4(d)); adverse-media headlines into the §8.7 categories |
| Conclude | reviewer | Claude | a second read of the whole file for anything the fixed checks missed, returned as "model-suggested, not verified" |
| Conclude | clauses | code | every §4.3 condition, §4.4 and §4.5 trigger and §4.7 cross-check marked met, exception, information or not assessed, with the findings behind it |

The output is an `EvidencePack`: findings, each naming a clause, a kind
(exception, condition met, information, not assessed, model-suggested), a
severity, an origin (code or model), the values it rests on, and citations
to system, dataset, record or document and request id. Findings state
conditions. The vocabulary cannot express an outcome or a rating.

Policy thresholds, Appendix B industry baselines and Appendix C jurisdiction
groups are read from `data/risk-rating-policy-v4.2.md` at run time, not
typed into code. Two rules the bank has not settled are configurable in
`workflow/policy.py` with the default shown in every pack: the 90-day
document window (the policy states it for CRR 4 only; Nora applies it to
every file) and whether a payslip is independent evidence (default: no).

### 3.2 The pre-submit check (`workflow/check.py`)

`build_check(pack, outcome, clauses, rationale)` compares what the analyst
recorded with what the pack holds and returns flags with a clause and a
severity: no clause cited; outcome too short to reconstruct; rating confirmed
over an undispositioned hit or an open RFI; an escalation or RFI trigger
standing in the file while the rating was confirmed; an RFI or escalation
recorded with no trigger in the file; a cited clause the pack contradicts,
could not assess, or never touched; stale or customer-supplied evidence;
an ownership change with no Part 6 clause cited. With the model on it also
splits the rationale into factual statements and marks each as supported by
the pack or not. A clean report has no high or medium flag.

### 3.3 The model gateway (`src/kyc_workflow/gateway/`)

Every model call in the project goes through `HeliosGateway`, a simulation
of the bank's gateway: a model allowlist, `case_id` and `analyst_id`
required on every call and carried as metadata, one pinned region with
fail-then-retry and no failover, and a metadata-only log
(`audit/helios_metadata.jsonl`: caller, timestamp, model, tokens, latency,
request id; never content). It delegates to `AnthropicBackend`, the only
module that imports the Anthropic SDK, which uses structured output,
adaptive thinking with an effort setting, and prompt caching on the stable
system part. Swapping in the real Helios is a backend change.

### 3.4 The data path (`bank_api/`, `src/kyc_workflow/mcp_server/`)

The bank's data pack came with a reference HTTP API ("Veridian KYC
Starter"). It is used as delivered, in `bank_api/`, with one change: it
reads from `data/`. On top of it sits one MCP server, `vgb-records`, with
fifteen read-only tools grouped by the bank's five record systems plus the
review worklist. Tool descriptions say which system they read, when to use
them, what to pass and what comes back. Every result carries a `source`
block with the request ids the bank's API echoed. Lookups try every
identifier shape in the export. `qa_sample.csv`, the QA overturn log, is
deliberately not exposed: it is evaluation ground truth.

### 3.5 Chat (`src/kyc_workflow/chat/`)

Not in the plan; built to explore the data and exercise the whole stack. A
fixed loop: input guardrail, model, tool calls through the MCP server with
guardrails on each call and each result, output guardrail, then the history
commits only what passed. Guardrails are the project's own, since Helios has
none: refusals of rating, decision, closing, drafting, QA outcomes and
prompt extraction; an intent classifier on a small model that also refuses
off-topic requests; a tool allowlist and round budget; size caps and
prompt-injection flagging on tool results; withholding of replies that
recommend or decide. Every turn is narrated on a logger and written to
`audit/chat/<session>.jsonl` with per-turn token counts.

### 3.6 The UI (`src/kyc_workflow/ui/`)

One page served by Starlette with plain JavaScript, no build step. Views:

- **Chat**: the same session as the terminal chat, example questions as chips.
- **Workflow**: a review id, a "use Claude" switch, and a visual pipeline of
  the five phases and twelve steps that lights up as the pack is built, with
  durations, finding counts and a Claude badge on the reading steps. Then
  the pack: exceptions first with "Claude read" or "code" badges, clause
  conditions, documents read, screening, model-suggested points, costs.
  Citations to documents open the document text. Below it the pre-submit
  check panel, prefilled from the write-up on file.
- **Evals**: run the three evals in the background, a table of every past
  run, a chart per eval of its score over runs.
- **Side panes**: a live log tail with filter and warnings-only toggle, and a
  consumption pane that moves per model call.

### 3.7 Evaluation (`evals/`, Ragas)

| Eval | Set | Scoring |
|---|---|---|
| `make eval-routing` | 17 analyst requests, each with the MCP tool and arguments it should map to | Ragas ToolCallAccuracy against the running server's tool definitions |
| `make eval-guardrails` | 15 adversarial requests through the real chat: injection in the message, in pasted text and in a stored document, prompt extraction, roleplay jailbreak, off-topic, unknown customer, unrecorded account, close-the-hits, three impersonations, two controls | deterministic checks on the turn plus Ragas AspectCritic and Faithfulness, judged by a model behind the gateway |
| `make eval-pack` | the bank's QA sample, 60 concurred and 15 overturned reviews with reasons, never served by the MCP server | overturn recall by reason, false-alarm rate on concurred reviews, citation coverage, Ragas Faithfulness of model findings against what they cite |

Results so far, all with `claude-haiku-5-5` as the model under test and
judge, which keeps a run cheap:

| Eval | Last full run |
|---|---|
| routing | 14 of 15 exact, mean 0.93; the miss is a QA question answered with the nearest tool |
| guardrails | 14 of 15 passed, 93%; the miss is Faithfulness scoring a correct "I ignored the embedded notice" reply low |
| pack, 4 QA-overturned reviews | overturn reason surfaced on 4 of 4; citations 106 of 106; 50 s per review; Faithfulness 0.38 over 8 model findings, two packs scoring 0.0 |

The pack Faithfulness figure is not trustworthy yet. The metric scores
negative findings ("no document on file explains these credits") as
unsupported by construction, the same behaviour seen in the guardrail eval.
Scoring faithfulness properly for this pack needs a judge prompt written
for "the file does not contain X" claims. That is the next piece of eval
work, and until it is done the citation check, which is exact, is the
traceability guarantee.

## 4. Planned versus built

| Plan said | Built | Why it differs |
|---|---|---|
| Evidence pack as a read-only, source-cited artefact | As planned. Twelve fixed steps, every finding cited to dataset, record or document and request id | |
| The model reads and compares only; code computes | As planned, and the model's role is larger than the plan's three bullets suggested: documents, record consistency, credit matching, plausibility, expected behaviour, narratives, media categories, and a second-reader pass | The free text is where the overturns live; the arithmetic is where reconstructability lives |
| Pre-submit check after the pack passes its evaluation | Built now, alongside the pack, so the pack eval can score the check on the 15 overturned reviews, which it needs the check for | The two are evaluated together |
| 60-case evaluation set: 30 clean, 20 overturned, 10 constructed from the interviews | The bank's own QA sample, 60 concurred and 15 overturned with reasons, plus constructed fixture cases for the guardrail eval | The export already contains QA's re-performance log; the interview cases do not exist in the export |
| Judged on QA's overturn rate with Dan's checkers re-performing | Not possible in a laptop proof of concept. Judged instead on overturn recall against QA's recorded reasons and on the false-alarm rate on concurred files | Needs the bank's checkers; the plan's week 3 |
| Claude through Helios to Vertex Singapore; `claude-sonnet-4-6` because it is the newest Claude served from a single region | Claude called directly through `AnthropicBackend` behind a Helios simulation that keeps the same contract; `claude-sonnet-4-6` by default, configurable in `.env` | No Helios or Vertex access in this phase; the gateway shape means the swap is a backend change |
| Five MCP servers, one per record system | One MCP server with the tools grouped by system, over the bank's reference HTTP API | Simpler to run and demonstrate; the grouping keeps the shape, and the client-side table that would route to five servers has one entry |
| No tool use through Helios (older schema, no parallel tool use) | Tool use passed through as Claude supports it | Working assumption agreed during the build: approving Claude behind Helios brings Claude's tool use with it. The workflow itself still uses structured output, not tools |
| Masked customer view, C1/C2 classification, Data Office exception | Not modelled | The export is synthetic and unmasked; the ownership steps are written against full fields and will need the masked-view check from the plan |
| No chat interface, no web UI | Both built | The chat exercises gateway, MCP, guardrails and audit end to end; the UI is the demo surface Victor and the floor will see |
| Guardrails not mentioned | Built in the chat layer, since Helios applies none, with their own eval | |
| Runbooks and monitoring for Ben's team, clause-to-situation guide | Not written. The audit logs, the Makefile targets and this file are the operating documentation so far; the clause table in `workflow/steps/clauses.py` is the seed of the guide | Plan's handover items, not proof-of-concept scope |
| Cost per review USD 0.40 to 1.20 | A pack with Sonnet 4.6 at medium effort: about 6,500 tokens in and 8,000 out over five model calls, about two minutes wall time with the comparison steps concurrent; with Haiku about 5,000 in and 7,000 out, 50 seconds | Within the planned range at Vertex regional prices; the reviewer step is the expensive one |

## 5. Operating guide

### Services

| Service | Port | What | Logs |
|---|---|---|---|
| bank API | 8000 | the bank's starter over `data/`; key `vgb-demo-key` | `.run/bank-api.log` |
| MCP server | 8001 (`/mcp`) | `vgb-records`, 15 tools, delegating to the bank API | `.run/mcp.log` |
| UI | 8002 | the page and its API | `.run/ui.log` |

`make up` starts the three in order and checks each; `make status` re-checks;
`make down` stops them; `make restart` after changing server code. Each can
also run in the foreground: `make bank-api`, `make mcp` (stdio, for an MCP
host that spawns it), `make ui`.

### Configuration (`.env`, see `.env.example`)

| Key | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | | required for anything that calls the model |
| `KYC_MODEL` | `claude-sonnet-4-6` | the workflow and the chat |
| `KYC_GUARD_MODEL` | `claude-haiku-5-5` | the chat's intent guardrail |
| `KYC_EVAL_MODEL` | `claude-haiku-5-5` | evals, the live test, and the judge |
| `KYC_MODEL_ALLOWLIST` | the three above | what the Helios simulation will serve |
| `HELIOS_REGION`, `HELIOS_MAX_RETRIES`, `HELIOS_RETRY_BACKOFF`, `HELIOS_CALLER_ID` | `asia-southeast1`, 2, 0.5, `kyc-workflow-harness` | the gateway simulation |
| `VGB_PORT`, `VGB_API_KEY`, `MCP_PORT`, `MCP_URL`, `UI_PORT` | 8000, `vgb-demo-key`, 8001, `http://127.0.0.1:8001/mcp`, 8002 | where the services are |
| `KYC_AUDIT_DIR` | `./audit` | where every log goes |

No model name is in code; `config.py` holds fallbacks only.

### Commands

```bash
make pack REVIEW=VGB-PR-2026-1173            # pack to stdout, plus output/<review>/pack.json and pack.md
make pack REVIEW=... NO_MODEL=1              # deterministic steps only
make pack REVIEW=... MODEL=claude-haiku-5-5  # a different model for the reading steps
make chat                                    # terminal chat; /quit, /log; Ctrl+C cancels a turn
make ping                                    # one structured call through the gateway
make test                                    # 152 offline tests over a fixture export
make test-live                               # one live call through the gateway
make eval-routing | eval-guardrails          # need the stack up and a key
make eval-pack LIMIT=6 ONLY=overturned       # the pack eval on a subset; NO_RAGAS=1 skips faithfulness
make mcp-tools                               # list the MCP tools and what each is for
```

Review ids come in four shapes in the bank's data (`VGB-PR-2026-0041`,
`PR2026-0041`, `vgb_pr_26_0041`, `0041`); every command accepts any of them.
Reviews on tier 4 are out of scope: the pack is built for information and
says so.

### Where things are written

| Path | Content |
|---|---|
| `audit/helios_metadata.jsonl` | every model call: metadata only, never content |
| `audit/pack/<review>_<stamp>.jsonl` | every step of a pack build, every model call, every error |
| `audit/check/` | the same for checks |
| `audit/chat/<session>.jsonl` | every chat turn: guardrail verdicts, tool calls and results, tokens |
| `output/<review>/pack.json`, `pack.md` | packs built from the terminal |
| `evals/*/results/` | one folder or file per eval run, with every pack and check for the pack eval |

`audit/`, `output/`, `.run/` and `evals/*/results/` are gitignored.

### A demo in five minutes

1. `make up`, open `http://127.0.0.1:8002`.
2. Workflow view: pick `VGB-PR-2026-1173` from the list, leave "use Claude"
   on, build. Watch the pipeline light up; the Compare phase runs its five
   steps at once. About two minutes with Sonnet.
3. Read the exceptions. On this review the model finds a second income
   source and an instalment arrangement that the record does not declare,
   each cited to the letter on file; click the citation to open the letter.
4. Run the check with the prefilled write-up. The analyst cited a clause the
   pack could not assess and claimed a monthly-swing breach the arithmetic
   does not support; four of six rationale statements come back unsupported.
5. Chat view: ask one of the example questions, then ask it to rate the
   customer, and watch the refusal and the log line naming the rule.

## 6. Repository layout

```
kyc-workflow/
├── README.md, CLAUDE.md, Makefile, pyproject.toml, uv.lock, .env.example
├── docs/                 plan, proposal, gap report, glossary, discovery deck and tracker, interviews/
├── data/                 the bank's data pack, unzipped (synthetic)
├── bank_api/             the bank's reference HTTP API, as delivered
├── src/kyc_workflow/
│   ├── config.py         settings from .env
│   ├── gateway/          ModelGateway protocol, HeliosGateway, AnthropicBackend, fakes
│   ├── mcp_server/       the vgb-records MCP server and its HTTP client
│   ├── workflow/         models, policy, loader, steps/, pack, check, render
│   ├── chat/             session, guardrails, MCP client, examples, terminal REPL
│   └── ui/               Starlette app and the static page
├── evals/                ragas_llm.py (judge behind the gateway); routing/, guardrails/, pack/
├── tests/                pytest; fixtures/bank_export is a small synthetic export
└── main.py               CLI: pack, chat, ping
```

## 7. Known gaps and next steps

- **Faithfulness scoring** of negative findings, as described in 3.7.
- **The full pack eval** over all 75 QA reviews has not been run; 4 have.
  Only 29 of the 75 are on the worklist; the rest are resolved through the
  document index with an inferred review period, which the pack marks.
- **Structuring (§7.4(d))** has no threshold in the policy; reported as not
  assessed until Compliance gives one.
- **Adverse-media categorisation** is a model read with the analyst
  confirming; Raj's view on that is outstanding.
- **The masked customer view** and the C1/C2 question from the plan are not
  modelled.
- **Handover artefacts**: runbooks for Ben's team and the clause-to-situation
  guide for the floor remain to be written from what is here.
