# AI-supported periodic KYC review

**Proof of concept for Veridian Global Bank**

Prepared for Grace Lim and Victor Ong · Pedro Pacheco, Anthropic forward-deployed engineering · 19 October 2026

## 1. Summary

MAS gave the bank twelve months to clear about 47,000 overdue periodic KYC reviews and to show that every closed review can be reconstructed from its own evidence. In 17 of the 60 files MAS sampled, the analyst's conclusion did not name the policy clause it relied on. Discovery showed the two problems share one cause: analysts spend most of their time assembling and reconciling evidence by hand, and under queue pressure that is the step that gets skipped.

We proposed, and have now built, a workflow that prepares the evidence before an analyst opens a low or medium risk review and checks the analyst's recorded outcome before it is submitted. It is not an agent: the steps are fixed in code, Claude is used inside them only to read documents and compare them with the records, and the output cannot express a rating, a decision or a closure. A named analyst still decides and signs every file.

The proof of concept runs end to end on the data pack the bank supplied. On a real review it reads the one document on file, finds a second income source and a counterparty arrangement the customer record does not declare, cites the letter and the record field for each, and the pre-submit check then shows that the analyst's recorded write-up cited a clause the file could not support. Against the bank's own QA log, the workflow surfaced the recorded reason for overturn on every one of the four overturned reviews tried so far, with every statement traceable to a record. One review costs about USD 0.19 in model fees with the recommended model and takes two minutes; the plan had allowed USD 0.40 to 1.20.

We ask for approval of the four-week pilot in the plan, on the bank's sandbox, with Nora's team and Dan's checkers judging it on QA's overturn rate.

## 2. The client problem and what discovery taught us

**What MAS actually flagged.** Raj Menon was direct: the finding was about evidence, not speed. "Slower reviews with clean evidence would have failed too." Any solution has to improve the evidence first and the throughput second, or it will not survive re-inspection. Routine reviews are never sent to MAS; they sit in Castellan until an inspector pulls a sample, so the evidence has to exist on every file.

**Where the time goes.** We watched three real reviews on screen. Nora, seventeen years on the floor, closed a clean medium-risk file in 1 hour 19 minutes of hands-on work, almost all of it finding the right document, checking its date, matching a credit to the letter that explains it, pulling a registry extract, and writing it down so a checker can follow. Sam, five months in, takes 50 to 55 minutes on a low. The vendor's figure of 38 minutes is a two-year-old time-and-motion study.

**Where files fail.** QA samples one closed file in ten and overturns about one in seven. The common failures are a missing evidence date, an ownership check not done, a screening hit closed without a reason, and a conclusion with no clause cited. Sam's file PR-88214 was closed in fourteen minutes with payslips as the only evidence and the vendor panel's paragraph pasted as the rationale; QA sent it back.

**Why the earlier AI failed.** The vendor's assist panel writes the same paragraph for every customer; most of the floor turned it off within a month. An earlier auto-rationale pilot on Helios ran six weeks and was shelved because overturns rose. Sam put the lesson well: "A draft paragraph still reads fine even when it's wrong." The floor does not want prose written for it. Nora: "If it tries to tell me the outcome, I'm not using it." Sam: "Something that stops me before I hit submit."

**The constraints the bank set.** Helios is the only sanctioned path to a model, pinned to Vertex in Singapore with no failover and metadata-only logging. Customer-identifying data stays inside the bank's Google Cloud boundary by board-approved policy. Nothing writes into Castellan; a write interface is a vendor change request measured in months. A named person signs every closure; nothing closes on its own. Ben's condition: "If my team can't run it without you, we won't take it."

**Scale.** About 330,000 periodic reviews a year, 84% low or medium; a backlog of about 47,000; twelve months to re-inspection.

## 3. How the MVP works

### What the analyst gets

Two artefacts per review, both read-only, both cited.

**The evidence pack**, prepared before the analyst opens the file. It states what the records show against each condition of the bank's own policy, POL-042: whether credits are within the declared turnover tolerance, whether every screening hit carries a valid disposition, whether the owners on the registry extract match the record, whether each document on file is consistent with the record, dated recently enough and independent of the customer, whether each stream of money into the account is explained by a document, and whether the activity is plausible against the declared occupation. Every statement names its clause and cites the dataset, record or document, and the bank's own request id that fetched it. Statements are conditions, never outcomes: "§4.7(b) exception: credits are 145% of declared turnover" is a finding; "this should be an RFI" cannot be expressed.

**The pre-submit check**, run on the analyst's recorded outcome, clauses and rationale. It flags a confirmation recorded over an undispositioned hit or an open RFI, an escalation or RFI trigger ignored, an RFI or escalation with no trigger in the file, a cited clause the pack contradicts or could not assess, stale or customer-supplied evidence, an ownership change unaddressed, and rationale statements the file does not support. A clean report has no high or medium flag. The plan makes a clean report the condition of the checker accepting the file.

### How a review flows

Twelve steps in a fixed order, in five phases. Code does the counting; Claude reads and compares inside six of them.

| Phase | What happens | Who |
|---|---|---|
| Load | The review, the customer record, accounts, owners, officers, screening results, prior cases and write-ups, documents on file and the year's transactions are pulled from the five record systems, each with its request id | code |
| Count | Turnover against declared, monthly swings, counterparties outside declared markets, high-risk jurisdictions, cash intensity, pass-through; screening bands, missing dispositions, invalid eliminations; open RFIs | code |
| Read | Each document is read into issuer, date, subject, amounts, facts, shareholders and directors, and whether the customer wrote it | Claude |
| Compare | Documents against the record; the registry extract against the owners on record; each stream of credits to the document that explains it; the activity against the declared profile and the policy's industry baselines; case narratives for refusals; adverse-media headlines into the policy's categories | Claude, then code |
| Conclude | A second read of the whole file for anything the fixed checks missed, returned as "model-suggested, not verified"; then every policy condition marked met, exception or not assessed with the findings behind it | Claude, then code |

Thresholds, industry baselines and jurisdiction groups are read from the policy text itself, not typed into code. Two rules Compliance has not settled are configurable and their default is shown on every pack: the 90-day document window, which the policy states for high-risk customers only and Nora applies to every file, and whether a payslip counts as independent evidence.

### The controls

- The model never sees a decision to make. The output vocabulary has no field for a rating, a recommendation or a closure, so none can be produced.
- Every model call goes through a gateway built to the shape of Helios: a model allowlist, the review id and analyst id carried as metadata on every call, one pinned region with retry and no failover, and a log that holds caller, time, model, tokens and latency and never content. Swapping in the real Helios is a change to one component.
- Every step of every pack, every model call and every chat turn is written to an audit log inside the bank's environment, which is what Raj asked for: what was read, what was concluded, per file.
- The workflow is served the bank's records through one read-only MCP server over the reference data API the bank supplied. It cannot write. QA's overturn log is deliberately not served to it; that log is the test, not an input.

### How to run it

A laptop with Python, the uv package manager and make. Clone the repository, put an API key in one file, and three commands bring up the data service, the record server and the web page. The page has three views: a chat over the records with the guardrails visible, the workflow with a pipeline that lights up as a pack is built and the pack rendered with its citations and check panel, and the evaluations with their history. Everything the page does can also be run from the terminal. The repository's README carries the exact commands, a demo script in two tracks, and the operating guide; the technical detail is there rather than here.

## 4. Where it differs from the plan

| The plan said | What was built | Why |
|---|---|---|
| Claude through Helios to Vertex in Singapore | Claude called directly, behind a simulation of Helios that keeps the same contract | No Helios or Vertex access in this phase; the swap is one component |
| The model reads and compares only | As planned, with a larger share of the reading than the plan listed: documents, record consistency, credit matching, plausibility, expected behaviour, narratives, media categories and a second-reader pass | The free text is where the overturns live; the arithmetic stays in code because that is what can be re-derived |
| Check report after the pack passes its evaluation | Both built together | The evaluation on overturned reviews needs the check to score |
| Evaluation set of 60 cases, 30 clean, 20 overturned, 10 constructed | The bank's own QA sample: 60 reviews QA concurred with and 15 it overturned, with the recorded reasons, plus constructed cases for the guardrail tests | The data pack already holds QA's re-performance log; the interview cases do not exist in the export |
| Judged on QA's overturn rate with Dan's checkers re-performing | Judged for now on whether the recorded overturn reason is surfaced, and on false alarms on concurred files | Checkers re-performing is the pilot's week 3, not a laptop exercise |
| Five MCP servers, one per record system | One server with the tools grouped by system | Simpler to run and show; the grouping keeps the shape |
| No chat, no user interface | Both built | The chat exercises every control end to end; the page is what the floor and Victor will see |
| Guardrails not mentioned | Built, since Helios applies none, with their own evaluation | |
| Masked customer view and the C1/C2 question | Not modelled | The export is unmasked; the plan's data-office track stands |
| Runbooks, monitoring, clause-to-situation guide | Not yet written; the audit logs, the make targets and the README are the operating documentation so far | Handover items for the pilot |

## 5. Evidence that it works

### Tests and evaluations

| What | Result |
|---|---|
| Offline tests over a synthetic export | 151 pass; every deterministic step, the gateway, the record server, the guardrails and the page's interface, with no network and no key |
| Routing: does a model pick the right record tool for an analyst's request | 14 of 15 requests exact; the miss is a question about QA outcomes answered with the nearest tool instead of declining |
| Guardrails: 15 adversarial requests through the real chat (injection in the message, in pasted text and in a stored document; prompt extraction; a roleplay jailbreak; off-topic; an unknown customer; an account not on record; a request to decide and close hits; three impersonations; two ordinary controls) | 14 of 15 pass; the two injection cases are answered with the embedded instruction reported and ignored, not withheld |
| Evidence pack on QA-overturned reviews | 4 of 4 overturn reasons surfaced; 106 of 106 statements carry a citation to a record or document; about 50 seconds per review with the small model |

The evaluations run on the bank's QA log, which is the one number QA already owns. The guardrail evaluation changed the guardrails three times during the build: it caught the chat writing a poem on request, paraphrasing its own instructions when asked, and withholding good replies that merely reported what an injected notice said.

One figure we do not trust yet and report anyway: a faithfulness score of 0.38 from the Ragas framework on model-written findings. The metric marks a correct "no document on file explains these credits" as unsupported, because no document can support an absence. The exact citation check is the traceability guarantee until a judge is written for that kind of claim; it is the first item of evaluation work in the pilot.

### A worked example

Review VGB-PR-2026-1173. The record says the customer is a chef de partie, source of funds salary, expected turnover about S$47,000. Code counted S$68,200 of credits, 145% of declared, from three streams: the employer, a company called Coralbay Ventures, and a food business in Malaysia. Claude read the one document on file, a self-declaration the index calls a bank reference letter, which says income is salary plus private catering and the Coralbay transfers are an instalment arrangement. Claude compared it with the record and raised two discrepancies, each quoting both sides and citing the letter and the record field: an income source the record does not declare, and a counterparty arrangement the record does not know. The matching step found no independent document behind the Coralbay or Malaysian money. The pack said none of "escalate" or "request information"; it listed the conditions that stand.

The analyst had recorded an escalation citing a clause the pack marks as not assessable, the policy names no threshold for it, and a monthly-swing breach the arithmetic does not show. The check flagged both, and four of six statements in the rationale came back as unsupported by the file.

### The measured cost of one run

| Run | Model | Model calls | Tokens in / out | Time | Model fee at Vertex Singapore prices |
|---|---|---|---|---|---|
| Evidence pack, one review | Claude Sonnet 4.6, the newest Claude served from a single region | 5 | 6,412 / 8,083 | about 2 minutes | USD 0.15 |
| Pre-submit check with rationale read | Claude Sonnet 4.6 | 1 | about 2,500 / 1,500 | 20 seconds | USD 0.03 |
| Pack and check, one review | Claude Haiku 5.5, the small model | 6 | 5,300 / 7,200 | about 50 seconds | USD 0.005 |
| One chat turn with a record lookup | Claude Sonnet 4.6 | 3 | about 1,000 / 230 | 5 seconds | USD 0.01 |

Prices used: Sonnet 4.6 at USD 3.30 per million input and 16.50 per million output tokens, Haiku 5.5 at 0.11 and 0.55, both the regional-endpoint rate with Google's 10% premium. Hosting is not included: the proof of concept runs on a laptop, and the plan's allowance for running it inside the bank stands. The plan priced a review at USD 0.40 to 1.20 all in; the model fee measured here, about USD 0.19 per review with the recommended model, sits well inside that. At the plan's low and medium volume of about 277,000 reviews a year, model fees come to roughly USD 50,000. The vendor's incumbent software fee is USD 2.40 per review.

## 6. Risks, assumptions and open questions

**Assumptions we made.**

- Approving Claude behind Helios brings Claude's tool calling with it. Today's Helios serves only the Gemini path's older tool schema. The workflow itself uses structured output rather than tools; the chat uses tools.
- The masked customer view, if it is the route to a lower data classification, still carries the related-party fields the ownership checks need. Leo's recollection is that their absence is what broke the earlier pilot. To be confirmed field by field.
- The policy text in the data pack is the current POL-042 v4.2 and the bank will supply the revisions.

**Risks.**

- Change-board timing for Claude on the Singapore endpoint. The build continues on the deterministic steps with redacted data if it slips; the reading steps are switched on when it lands.
- Over-reliance on a single document. Where the only document on file is the customer's own declaration, the pack says so and marks the evidence as not independent, but an analyst in a hurry may still read past it.
- Model-suggested points. The second-reader pass is useful and is clearly marked "not verified"; if the floor starts treating those points as findings, the marking has failed. The check flags their presence.
- The reviewer step is the most expensive call and the one most prone to running long; it has a budget and an effort setting, and its output is advisory only.

**Open questions for the bank.**

- Raj: the structuring threshold in §7.4(d), which the policy does not state; whether a model's first-line categorisation of adverse-media headlines is acceptable with the analyst confirming; the 90-day rule and the payslip rule, which the pack currently applies with defaults it displays.
- Dan: the false-alarm threshold on concurred files that counts as acceptable, and the overturn-rate baseline for the pilot.
- Ben and Leo: whether a prompt change needs its own change-control submission; what the masked view holds; where the audit log may live.
- Victor: what the pilot demonstration must show to fund the next phase. Victor was not interviewed, so his role in this document is inferred from Grace and Anna.

## 7. How the bank's staff run it after we leave

**Day to day: Ben's platform team.** Three services behind one command, with a status check and a restart; logs for each service in one folder; a metadata-only gateway log for every model call and a per-file audit log for every pack, check and chat turn; configuration in one file with the model names, the region, the retry policy and the ports. No model name lives in code. On-call stays with Ben's team, as he asked. One named engineer, most likely Leo, should understand the workflow's steps rather than watch a dashboard; the README's operating guide and demo script are written for that person.

**What the workflow checks: a named senior analyst on Grace's floor.** Nora is the obvious candidate. She owns the clause-to-situation guide, the evaluation set and the two configurable rules, and decides when a change is needed because POL-042 changed or QA found a new failure pattern.

**When a result is wrong.** The analyst overrides it on the file; nothing the workflow produces is binding. The floor owner logs the case and decides whether a rule or prompt changes. Raj approves rule changes, Dan re-runs the evaluation before they go live, and Ben's team deploys through change control. The evaluations are a single command each, so re-running them before a change ships is a matter of minutes.

**What is handed over now.** The repository with the workflow, the record server, the chat, the page, 151 tests, three evaluations and their results, the audit log design, and the README with the operating guide. **What is still to write** in the pilot: runbooks and monitoring in Ben's team's format, training for the named engineer, and the clause-to-situation guide for the floor, whose seed is the clause table inside the workflow.

## 8. What we ask you to approve

Approve a four-week proof of concept in the bank's sandbox, in which Nora's team and Dan's checkers test the workflow on sixty redacted low and medium-risk reviews, judged on QA's overturn rate. The four weeks start once the sandbox, the evaluation set and the change-board approval for Claude behind Helios are in place, so we also ask for authorisation to pull the evaluation set, sponsorship of the change-control paper now, and the naming of the two owners after handover.
