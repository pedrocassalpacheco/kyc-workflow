# VGB Periodic KYC Review: What We Learned and the Proof of Concept We Propose

**For:** Grace Lim (Head of Financial Crime Operations) and Victor Ong
**From:** Anthropic forward-deployed engineering
**Status:** Discovery complete. Decisions requested in section 7.

---

## 1. Summary

MAS gave Veridian Global Bank twelve months to clear a backlog of about 47,000 overdue periodic KYC reviews and to show that every closed review can be reconstructed from its own evidence. Discovery with eight people across Operations, Compliance, QA, Platform Engineering and Vendor Management shows the two problems share one root cause: analysts spend most of their time assembling and reconciling evidence by hand, and under queue pressure the evidence step is the one that gets skipped.

We propose a proof of concept (POC) in which Claude prepares the evidence for each low and medium risk review before the analyst opens it, and checks the analyst's work before it is submitted. The analyst still decides, writes and signs. Nothing closes a file on its own, and nothing writes into Castellan. The POC will be judged on one number QA already owns: the overturn rate on files prepared with the tool must be at or below today's rate.

This is deliberately not a rationale-writing tool. The bank has tried that twice, and both times QA overturns went up.

---

## 2. What MAS actually flagged

The inspection letter (finding 4.3, rated High) says two things, and the second is the one that will decide re-inspection:

| Finding | What it means for the bank |
|---|---|
| About 47,000 reviews overdue, about 84% of them low or medium risk | The backlog. Volume problem. |
| In 17 of 60 sampled rationales, the conclusion was recorded without naming the policy clause relied on | The evidencing standard. Quality problem. A faster backlog with the same rationales would still fail. |

Raj Menon (Deputy MLRO) was direct about this: "slower reviews with clean evidence would have failed too." Any solution has to improve evidence first and throughput second, or it will not survive re-inspection.

Scale of the job:

| Figure | Source |
|---|---|
| About 330,000 periodic reviews a year, 84% low or medium | Grace |
| Backlog of about 47,000, mostly low and medium | Grace, MAS letter |
| Twelve months to re-inspection | MAS letter |
| QA re-performs a random 1 in 10 of closed files each month | Dan Koh |

---

## 3. How a review really works today

We followed three real reviews on screen rather than relying on process documents.

**Where the time goes.** Nora (senior analyst, 17 years) closed a clean medium-risk file in 1 hour 19 minutes of hands-on work spread over 13 calendar days, 7 of which were waiting for one document from the branch. Almost all of the hands-on time was reading and typing, not deciding: finding the right document among eleven, checking its date against the 90-day rule, matching a credit to the document that explains it, pulling a fresh registry extract, and writing it all down so a checker can follow it without calling her. Sam (5 months) takes 50 to 55 minutes on a low. The vendor's 38-minute figure is from a time-and-motion study a couple of years old.

**Where files fail.** QA's common failures are missing evidence dates, ownership checks not done, and screening hits closed without a reason. Two live examples:

- Sam's PR-88214 was closed in 14 minutes with payslips as the only evidence, the vendor panel's paragraph pasted as the rationale, and no clause named. QA overturned it.
- Nora's VGB-C-088410 (a dormant holding company) was closed by a junior analyst as "unchanged." The registry extract already on file showed a different 30% shareholder and a new director who had never been screened, and a payment of about forty thousand dollars had gone to that shareholder. QA overturned it. Every fact needed to catch this was already in the bank's systems.

**Why the clause goes missing.** The clause field in Castellan is labelled "optional." Nora fills it in every time because of the MAS letter. Sam leaves it blank because "nobody's ever told me which clause goes where." There is no written guide mapping clauses to situations, only a training deck and watching seniors.

**Why the existing AI assist failed.** The vendor's KYC Assist panel writes the same paragraph for every customer ("stable business activity, no anomalies noted") regardless of what is in the file. Most of the floor turned it off within a month. An earlier auto-rationale pilot on Helios ran for six weeks and was shelved because overturns rose. Sam, who still uses the panel, put the lesson well: "A draft paragraph still reads fine even when it's wrong."

---

## 4. What each stakeholder needs

| Who | What they said they need | What it means for the design |
|---|---|---|
| Grace (sponsor) | Backlog gone before MAS returns. "My analysts checking work instead of assembling files." Will make a clean check a hard stop before a file reaches the checker. | Optimise for analyst time on low and medium files. A process gate, not a voluntary side panel. |
| Raj (Compliance) | Every file reconstructable: clause, what was checked, what was found, who signed. AI may flag gaps, suggest a rating and draft, as long as a named analyst reads, edits and signs. Nothing closes on its own. Anything outside Castellan is not part of the record. | Human signs every file. The tool's output has to end up inside the case file. |
| Dan (QA) | Would re-perform off a check report. Will sign off only on sampled re-performance, overturn rate at or below today's, and a named owner per file. | The success metric is QA's own metric. QA is part of the evaluation from day one. |
| Nora (senior analyst) | "I'd want to see the document it read, not just a line it wrote." Fetch dates, numbers and registry data; leave the judging to her. | Every statement cites its source document. The tool does not suggest outcomes. |
| Sam (junior analyst) | "Something that stops me before I hit submit," not a drafting tool and not a panel he has to remember to open. | Pre-submit check, enforced by process. |
| Ben and Leo (Platform) | Everything model-shaped goes through Helios, the bank's AI gateway. Read-only via the five MCP servers (Ben's data connectors, one per system of record). No write-back to Castellan this year. Change control alternate Thursdays. "If my team can't run it without you, we won't take it." | Simple, deterministic harness. Runbook, monitoring and a named owner on Ben's team are deliverables. |
| Anna (Vendor Management) | An all-in USD cost per review to put next to the incumbent's USD 2.40 software fee. | Preliminary estimate: USD 0.40 to 1.20 per review all in, firmed up during the POC. The productivity case goes to Grace and Victor separately. |

---

## 5. What we propose to build

Following Anthropic's guidance to use the simplest architecture that meets the requirement, the POC is a deterministic workflow with one constrained Claude reasoning step and human approval at every decision point. It is not an autonomous agent.

**Two outputs per review, both read-only, both cited to source documents:**

1. **Evidence pack, prepared before the analyst opens the file.** What changed since the last review. Each material credit matched to the document that explains it, with the document's date, its age against the 90-day rule and whether it is independent of the customer. Screening hits alongside their previous dispositions. Ownership on file compared with the registry extract on file, with staleness and unscreened parties flagged. The POL-042 clauses the evidence points to, each linked to the evidence.
2. **Pre-submit check, run on the analyst's completed work.** Missing or unnamed clauses. Expired or non-independent evidence. Screening alerts carried forward without a reason. Ownership changes without a registry extract. Open requests for information on a file about to close. The analyst attaches the check to the case so it becomes part of the record.

**Control boundary.** Every capability is classified by who has authority, as the discovery method requires.

| Claude may do | Needs analyst confirmation | Human only |
|---|---|---|
| Retrieve from the five read-only data connectors (MCP servers) | Suggested clauses | Risk rating decision |
| Compare current file with prior review and registry extract | Flagged gaps and stale documents | Disposition of screening hits |
| Extract dates, amounts and parties, with citations | Draft text, if Grace and Raj later choose to allow it, sentence by sentence cited | Rationale and recommendation |
| Produce the evidence pack and check report | | Sign-off and closure |
| | | Any write to Castellan |

**Scope.**

| In the POC | Not in the POC |
|---|---|
| Low and medium risk periodic reviews (about 84% of the backlog) | High risk files (same evidence, extra Compliance sign-off; a follow-on) |
| Individuals and companies | Fresh company registry checks (no integration exists; the analyst keeps buying the registry profile from inside Castellan as today, and the workflow only flags when the one on file is stale) |
| The five existing MCP servers, read-only | Any write-back to Castellan |
| Claude Sonnet 4.6 on Vertex AI in Singapore via Helios (the newest Claude served from that regional endpoint) | Direct calls to any model provider |
| Redacted or synthetic case files inside the bank's sandbox | Production customer data |

---

## 6. How we will prove it works

Anthropic's guidance is to set measurable success criteria before building, evaluate against real historical cases, and scale gradually. The POC has one primary gate and explicit stop conditions.

**Evaluation set.** 60 closed low and medium risk reviews, the same sample size MAS used, pulled from Castellan and redacted with Grace's or Raj's authorisation: 30 that passed QA, chosen at random from the last six months; 20 that QA overturned, covering the mix Dan and Raj asked for (ownership changes, stale documents, screening carry-forwards, customer-supplied evidence), including PR-88214 and VGB-C-088410; and 10 constructed cases for situations too rare or sensitive to pull, including attempts to make the tool close a file or change a rating. Sam's PR-88301 is high risk and was never seen by QA, so it is used only to exercise the check logic and is not counted in the set.

**What we measure.**

| Measure | Owner | Pass condition |
|---|---|---|
| Overturn rate under QA re-performance on tool-assisted files | Dan | At or below today's rate (today's rate to be supplied by QA) |
| Clause named on every closed rationale | Raj | 100% on the evaluation set, against MAS's 17 of 60 failure |
| Known defects caught by the pre-submit check (missing clause, stale document, unscreened party, open RFI) | Anthropic and Nora | Agreed recall target set with Nora before the build |
| Every statement in the pack traceable to a source document | Nora | No uncited claims. One hallucinated fact is a defect, not a statistic |
| Analyst hands-on time per file | Grace | Measured against Nora's 1h19 and Sam's 50 to 55 minutes |

**Stop conditions, agreed with Raj.** No named person accountable for a closure. Evidence that cannot be reconstructed per file. QA not signed off on the approach. Any of these stops rollout regardless of the other numbers.

**Demo to Victor.** Nora and Dan re-perform real redacted cases with and without the evidence pack, on screen. The demo shows the pack, the check, the citations, and QA's result, not a slide.

---

## 7. Decisions we need from Grace and Victor

1. **Confirm the artifact.** Evidence pack plus pre-submit check, with any drafted text as a later option only if every sentence is cited. Grace is content with either; Raj permits drafts; the floor and QA history argue for the check.
2. **Make the check a process gate.** A file is not accepted by the checker without the check report attached. Grace said she would push for this. It needs Raj to accept an analyst-attached report as part of the record, since there is no system write-back this year.
3. **Authorise the evaluation set.** Grace or Raj signs off the pull of redacted passed and overturned cases from Castellan. Nothing moves until this is done.
4. **Sponsor the Claude approval track in parallel (Victor).** Adding Claude behind Helios needs a change control paper from Ben's team, a decision on whether Claude on Vertex Singapore counts as a new outsourcing arrangement under VGB-DC-07, a model risk view, and Vendor Management paperwork. None of these has an owner. Run in parallel, they fit inside the POC. Run after it, they become the critical path.
5. **Name the day-to-day owner after handover.** Ben's team for the platform. Someone needs to own the prompts and evaluation set when policy changes. Grace and Raj both said they want this named before anything goes near production.

---

## 8. POC plan

A four-week proof of concept. The clock starts only when the prerequisites below are in place, because each of them takes a week or more and none has been started.

**Before day one (prerequisites, owned by the bank with our help)**

| Prerequisite | Owner | Lead time |
|---|---|---|
| Sandbox and consumer forms submitted; service account with read scopes on the five MCP servers | Ben, Leo | About a week each once the forms are in |
| Change control paper for Claude Sonnet 4.6 on the Singapore endpoint behind Helios, approved by the board | Ben writes, Victor sponsors | Board sits alternate Thursdays |
| Evaluation set of 60 cases pulled from Castellan and redacted | Grace or Raj authorise, Ben's team extracts | To be confirmed with Ben |
| Data pack: POL-042 v4.2 text, masked customer view field list | Ben | With the sandbox |
| Pass criteria written down with Dan and Nora; today's overturn rate from Dan | Dan, Nora | One working session |

**The four weeks**

| Week | What happens | Depends on |
|---|---|---|
| **1 to 2. Build** | The harness (the software around Claude that runs the workflow) inside the bank's Google Cloud boundary, calling the five data connectors. Evidence pack first, then the pre-submit check, against the evaluation set. Audit log of every retrieval and claim kept inside the bank's environment. Clause-to-situation guide drafted with Raj for 5.4, 6.5, 6.6 and 8.4. | All prerequisites |
| **3. Evaluate** | Nora reviews extraction, clauses and screening calls against real files. Dan re-performs tool-assisted cases. Defects fixed, numbers recorded. | QA time in week 3 |
| **4. Demonstrate and decide** | Demo to Victor with Nora and Dan. Cost per review range to Anna, firmed up from the preliminary USD 0.40 to 1.20 using measured token counts. Productivity case to Grace and Victor. Decision on the larger engagement and the order form. | Order form through Legal for anything beyond the POC |

**If Claude approval slips.** The build continues on redacted data with the deterministic checks (document age, missing extract, open RFIs, clause coverage) and the model step is swapped in when the board approves. The four weeks do not start until it has.

**What we deliver at the end.** The working harness in the sandbox, the evaluation set and results, the audit log design, a runbook and monitoring sketch for Ben's team, the clause guide, and the two commercial figures.

---

## 9. Risks we are tracking

| Risk | Why it matters | Mitigation |
|---|---|---|
| Masked customer view drops names and related-party fields | Ownership checks (6.5 and 6.6) need exactly those fields. This is what broke the earlier pilot. | Confirm with Leo field by field. If missing, request the Data Office exception now (weeks to months) and build the rest in parallel. |
| Claude approval timing | Helios serves only Gemini today. No defined process for a new model vendor. | Victor sponsors the track. Paper drafted with Ben before the plan is agreed so it lands at the first available Thursday board. |
| Model choice is fixed by the region | Anthropic's documentation says the newest Claude models on Vertex are served only from global or US and EU multi-region endpoints. Single-region endpoints such as Singapore serve Claude Sonnet 4.6 and earlier. | Name Sonnet 4.6 in the change control paper and build against it. Confirm the Singapore rate with the GCP account rep. |
| Check report lives outside Castellan | Raj: not part of the record. | Analyst attaches it to the case. Raj to confirm this is acceptable. |
| Two rules are applied inconsistently today | 90-day document rule: Nora applies it, QA's checklist does not name it. Payslips: QA accepts them for cross-border income, Nora and PR-88214's overturn do not. | Settle both with Raj before they are encoded. The POC will expose other cases like these, which is useful. |
| Prompt logging | Infosec ruled out prompt logging at Helios. Our own audit log inside the bank needs the same ruling. | Raise through Ben's change control paper. |
| Sandbox and data exception timing | Nothing has been submitted yet. | Submit the forms this week. |

---

## 10. What success opens up

If the POC passes QA's gate, the same harness extends to high-risk files (same evidence, plus Compliance sign-off), to the checker's workflow, and, when Ben's team is ready for the vendor change request, to a gate inside Castellan's submit flow. The clause guide and the evaluation set become bank assets independent of any vendor. The commercial case has two parts: a per-review cost for Anna to compare at renewal, and the analyst-time and QA-rework case for Grace and Victor, which is where the larger value sits.
