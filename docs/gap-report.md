# VGB KYC Agent: Discovery Gap Report

Prepared before the Grace and Victor meeting. Based on interviews with Grace, Raj, Nora, Ben, Leo, Anna and Sam.

## Bottom line

Discovery has settled the problem. MAS flagged evidence, not speed. Closing rationales didn't name the clause relied on, so decisions couldn't be reconstructed (Raj). The backlog adds pressure on top of that. Discovery has also settled most of the technical constraints. Three decisions are still open, and they block the design:

1. **What the agent produces.** Nobody owns this yet. Ben and Nora both said it's Grace's call.
2. **Where it sits relative to Castellan.** The constraints mostly decide this already (read-only, no write-back this year), but nobody has agreed it.
3. **How Claude gets approved.** Helios serves only Gemini today, and there is no defined process for adding a model vendor.

Only the first is purely Grace and Victor's to decide. The other two need Ben, Security and Legal, but Grace and Victor can sponsor them.

---

## 1. What artifact the agent generates

**What we heard**

| Source | Said |
|---|---|
| Grace | "My analysts checking work instead of assembling files." |
| Raj | Every file needs clause, check, finding and names. High-risk files use the same content with an extra sign-off from Compliance. |
| Nora | "I'd want to see the document it read, not just a line it wrote." Fetching dates and numbers would help. "The judging part … stays mine." |
| Sam | "I'd rather something that just tells me what's wrong before I submit … A draft paragraph still reads fine even when it's wrong." |
| History | KYC Assist and the auto-rationale pilot both produced generic paragraphs. QA overturns went up, and the pilot was shelved. |

**Position to propose:** an **evidence pack plus pre-submit check**, not a rationale writer.
- **Before the analyst starts:** what changed since the last review, each material credit matched to a source document with its date, its age against the 90-day rule and whether it's independent, screening hits alongside their previous dispositions, ownership changes, and suggested POL-042 clauses linked to evidence.
- **Before submit:** check the analyst's rationale against the file. Look for missing clauses, expired or non-independent evidence, unaddressed alerts, ownership changes without a registry extract, and open RFIs.
- Every statement cites the document it came from. The analyst decides and signs.

**Still missing**
- Grace's agreement on the artifact, and whether a drafted rationale is ever acceptable, for example as an edit-only draft where every sentence has a citation.
- Raj has ruled (Q20): flagging gaps, suggesting a rating and drafting a first-pass rationale are all allowed as drafts; the analyst reads, edits and signs; nothing closes a file on its own. A cited draft is therefore acceptable to Compliance; whether it's wise is still the pilot's lesson.
- What makes a rationale pass QA. We haven't interviewed Dan Koh yet.
- Whether the artifact also has to serve the checker and Raj's team on high-risk files, or only the analyst.

## 2. Side by side with Castellan, or integrated

**What we heard**
- Not replacing Castellan (Ben, Nora).
- Read-only. "Nothing we build writes into it this year." A write interface would take months of change requests with the vendor (Ben).
- "Not touching what I sign" (Nora).
- Sam wants a gate: "Something that stops me before I hit submit, not something sat next to Castellan I have to remember to look at."

**The tension:** Without write access, we can't put a real gate inside Castellan's submit flow. The constraints force a separate tool, but the user most at risk of skipping it (Sam, under time pressure) is exactly the one who won't open a separate tool.

**Options to put to Grace**

| Option | How it's enforced | Trade-off |
|---|---|---|
| A. Side panel or separate tool | Voluntary | Easiest to build. Likely skipped when analysts are behind. |
| B. Process gate | The checker won't accept a file without a clean check report referenced on it | No Castellan change. Needs Grace to change the process. |
| C. Castellan integration | Built into the submit flow | Months of vendor work and Ben said no this year, so not for the POC. |

**Still missing**
- Grace's decision. **Option B is the realistic proposal for the POC.**
- **Raj has now answered Q23: anything outside Castellan is not part of the record for MAS.** So the check report has to get into the file. With no system write-back this year, the only route is the analyst attaching it themselves (documents tab or rationale). Option B needs that step built into the process, and Raj needs to accept it.

## 3. Onboarding Claude (model approval)

**What we heard**
- Helios is the only sanctioned path, and nothing calls a model provider directly (Ben).
- Helios fronts Vertex AI in `asia-southeast1` with Gemini only, has no embedding models, and uses the older tool-calling schema (Leo).
- Adding a model goes through Ben and a security review (Leo).
- Bringing on a model vendor would be new for the bank. Ben handles the technical side, then Vendor Management does the paperwork. The process hasn't been defined (Anna).
- Our own research says Claude has regional endpoints in `asia-southeast1` (Sonnet 4.5/4.6, Opus 4.5/4.6). **We still need to check whether the current Claude 5 models are available there.**

**Still missing**
- **Security review is Ben's team.** There is no separate security person. A new model goes to the change control board (alternate Thursdays) with a paper behind it, and Ben says it "usually comes in through the plan once that's agreed." So agreeing the plan with Grace and Victor is on the critical path for Claude approval.
- **Model risk:** The discovery deck says to interview model risk, and we haven't. An AI used in a compliance process will almost certainly need model risk approval.
- Whether Claude can go on the existing GCP commitment or needs a new vendor line. Anna says Ben owns it; Ben says Anna does. Nobody owns it yet.
- Residency is settled: VGB-DC-07 (board-approved) requires C1 data to stay on sanctioned platforms in Google Cloud `asia-southeast1` via approved gateways. Claude on Vertex `asia-southeast1` fits the boundary. **Open:** whether it counts as a new third-party processing arrangement under 5.2, which would add Compliance notification, a technology risk assessment and Data Office sign-off.
- How long all of this takes end to end, which sets the earliest possible start for the POC on Claude.

**Ask of Victor:** sponsor the model approval track (Ben, Security, Model risk, Vendor Management) now, in parallel with the POC, so it doesn't become the critical path.

## 4. Data for the POC

**What we heard**
- There are five read-only MCP servers: customer master, screening, case history, document store and transaction summary (Ben).
- A masked customer view might count as a lower classification. Otherwise a data exception takes weeks (Ben).
- The masked view drops names and related-party fields, which is "the one that bit the pilot" (Leo). Ownership checks (6.5/6.6) need exactly those fields.
- The sandbox and redacted samples are covered by the existing letter (Anna). Nora can't share real files and says to ask Grace for test files.
- Nora buys a fresh **ACRA** registry profile (SGD 5.50) from inside Castellan on company files. There's no MCP route to a fresh pull, but extracts already on file are in the document store. The agent can compare the on-file extract with customer master and flag staleness; the fresh pull stays with the analyst.

**Still missing**
- Who produces the redacted or synthetic sample cases, and when (Grace).
- Whether the POC uses the masked view (which weakens the ownership checks) or goes through the exception process (weeks to months). VGB-DC-07 3.4 says masked data can be C2 with Data Office approval, so the Data Office is the contact for both routes.
- Confirm the document store MCP server exposes ACRA extracts with dates.
- The text of POL-042 v4.2, which Raj says will be in Ben's data pack. Confirm it's included.

## 5. Identity, security and audit

**What we heard**
- There's no on-behalf-of authorization. The likely setup is one service account for the agent with broad scopes, plus the analyst ID and case ID passed as data. This isn't decided and needs a security policy call (Leo).
- Helios has no redaction and no guardrails, and logs only metadata for 90 days. Infosec ruled out logging prompts and responses (Leo). Ben has since confirmed this: he meant metadata logging, not redaction.
- Provisioning takes a security form and about a week (Leo).

**Still missing**
- Security's sign-off on the identity model.
- Where our own audit and evaluation trail can live, and what it can contain, given Infosec's position on prompts.
- Ben confirms the harness must log its own reasoning inside the bank's environment, and that log becomes a change control item.

## 6. Success criteria, scope and evaluation

**Still missing (none of this has been defined)**
- **What the POC demo has to show** to open the larger engagement, and to whom (Victor?).
- **Scope:** which risk tiers and review types. About 85% of reviews are low or medium (Grace). There are also reviews from the 2024 backlog programme that were deferred on an RM attestation alone. Are those in scope?
- **Metrics:** Dan's sign-off criterion is overturn rate at or below today's under sampled re-performance, with a named owner per file. We don't yet have today's rate. Secondary: clause completeness, analyst time, time waiting on RFIs. Baselines: Nora took 1h19 hands-on, Sam takes 50 to 55 minutes on a low, and the vendor's time-and-motion figure of 38 minutes is old.
- **Evaluation set:** QA's overturned cases in Castellan are the best source (Dan). Ready-made test cases: Sam's PR-88214 and PR-88301, and Nora's VGB-C-088410 (Pelican Ridge Holdings: customer master and the on-file ACRA extract disagree on a 30% shareholder, a new director was never screened, and a SGD 40,000 debit went to the unrecorded shareholder; a junior closed it as "unchanged, dormant" and QA overturned it). Raj wants ownership changes, stale documents and screening carry-forwards covered.
- **What would stop a rollout** (Raj's open Q24).

## 7. Commercials, timeline and handover

**What we heard**
- Anna needs an all-in USD cost per review, as a range, to compare with the vendor's software fee of USD 2.40. Analyst time is excluded from that comparison and goes in the productivity case for Grace and Victor.
- Budget sits with Victor and Grace. Anna hasn't seen a budget line.
- Our order form is still with Legal. Production access waits on it.
- Change control runs every other Thursday (Ben). Provisioning takes about a week (Leo).
- "If my team can't run it without you, we won't take it" (Ben).

**Still missing**
- The date of the next MAS visit and the size of the backlog. Without these we can't size the work or the timeline.
- Whether there's a budget, and how big.
- Who owns the agent day to day after we hand over: Ben's team for the platform, but who owns the prompts and evaluations?

---

## Pending items by person

Everything still open, grouped by who can answer it. Starred (★) items are the ones to ask if time runs short. "Deferred by" shows who pointed us to this person.

Suggested order: Dan, Leo, Raj, Grace, Victor, then Ben again with the change control paper. Model risk and Legal once named. Nora, Sam and Anna as short follow-ups.

### Dan Koh (QA) — interviewed; remaining items

Answered: QA is pass/fail against the checklist, item by item, not tracked by category or analyst. Common fails: missing evidence date, ownership check not done, screening hit closed without a reason. A pass names the clause, has the evidence date and dispositions each hit with a reason. He'd re-perform off a check report and sees it as "closer to something useful." His sign-off conditions: sampled re-performance, overturn rate at or below today's, and a named person owning each file. Sampling is random, about one in ten closed files a month, unchanged since the MAS letter. He has no data from the shelved pilot. Evaluation set: clean lows, joiners and ownership changes, and known fails; pulling them is a data question for Grace or Raj.

1. ★ Will he sign off the approach formally once the evaluation shows overturn rate at or below current? Raj won't support rollout without it.
2. The 90-day document rule isn't on his checklist; he checks the evidence date "makes sense." Nora applies 90 days from memory. Which is the standard, and should the agent enforce 90?
3. Payslips: Dan says a payslip counts as independent evidence for cross-border income; Nora says payslips are "the customer vouching for themselves," and PR-88214 was overturned on that. Settle this before encoding it.
4. What is the current overturn rate? It's his pass criterion, so we need the number.

### Ben Tan (Head of Data Platform Engineering) — follow-up done; remaining items

Note: Castellan has a "Buy ACRA business profile" button and ACRA extracts sit in the document store, so registry data exists on file even though there's no MCP route to a fresh pull. The agent can compare the on-file extract against customer master and flag when it's stale.

Answered in the follow-up: redaction (retracted, Helios logs metadata only), security review (his team, via the change control board), sandbox (covered by the letter, about a week once the form goes in), failover (none, fail and retry), scoring formula (vendor's, never seen written down), handover needs, audit trail (harness logs it inside their environment), pilot retrospective (none written).

1. ★ The change control paper for adding Claude: what does it need to contain, and can we draft it with him so it's ready the moment Grace and Victor agree the plan? He won't docket it from a conversation.
2. Who signs the data exception for unmasked customer data (he'll check). Realistic timing is weeks to months.
3. Evaluation harness: he needs to see what it looks like before saying what his team needs from us. Bring a sketch.
4. Who on his team will be the person who "actually understands the harness".
5. Does the document store MCP server expose ACRA extracts and their dates? Needed for the ownership check.

### Leo (runs Helios) — follow-up (Ben pushed more to him)

1. ★ What's in the masked customer view, field by field? Does it keep related parties and ownership? (Ben didn't know.)
2. ★ Does a prompt change on its own trigger change control, and what does a submission need? (Ben said Leo runs the process day to day.)
3. ★ Identity: what does Helios and the MCP layer actually support: service account plus analyst ID logged, or anything more? Ben's instinct is the former but said "don't quote me".
4. The exact model version strings in the gateway config (he offered to check).
5. What the sandbox and consumer forms need from us, so both can go in now and the week starts.
6. Does Helios support streaming and long context on the current Gemini path, in case we prototype there before Claude is approved?

### Raj Menon (Deputy MLRO) — follow-up done; remaining items

Answered: AI may flag gaps, suggest a rating and draft a first-pass rationale, as long as the analyst reads, edits and signs; nothing closes a file on its own. Audit needs the file reconstructable per customer, and anything outside Castellan is not part of the record for MAS. Rollout stoppers: no named person accountable, evidence not reconstructable, QA not signed off on the approach. POL-042 v4.2 is current and will be in Ben's data pack. Residency is internal policy (VGB-DC-07, board-approved), not MAS law. Evaluation set: ownership changes, stale documents, screening carry-forwards. High-risk files: same evidence content plus his team's sign-off. Weightings: vendor module on Grace's side; he wasn't involved.

1. ★ Does Claude through Vertex count as a new third-party processing arrangement under VGB-DC-07 5.2 (notification through Group Compliance, technology risk assessment against MAS TRM, Data Office sign-off), or is it covered by the existing Google arrangement? This decides how long Claude approval takes.
2. ★ If the check report has to be part of the record, is it acceptable for the analyst to attach it to the file in Castellan themselves (an analyst-mediated write), given there's no system write-back this year?
3. Clause wording sessions on 5.4, 6.5 and 6.6 once we have the POL-042 text. He offered.
4. Authorise the data pull for the evaluation set from Castellan (Dan says it's you or Grace).
5. Sam's PR-88301 (high-risk file confirmed with the source-of-funds RFI open): Raj says QA or he needs to look at it directly. Agree with Grace and Nora how this is handled before it reaches Sam. We surfaced it; it shouldn't land on him as a surprise.

### Grace Lim (Head of Financial Crime Ops, sponsor) — follow-up

1. ★ What should the agent hand the analyst: an evidence pack plus a pre-submit check, or a drafted rationale? Is a draft acceptable if every sentence cites its source? (Deferred by Ben, Nora and Sam.)
2. ★ Would you make a clean check report a condition of the checker accepting a file? Without Castellan write access, that's the only way the check can't be skipped. (Deferred by Nora and Sam.)
3. ★ How many reviews are in the backlog, split by risk tier, and when is MAS's next visit?
4. Which review types are in scope for the POC: low and medium only, or high too? Should we include the 2024 reviews deferred on an RM attestation alone?
5. ★ Who authorises pulling overturned and passed cases out of Castellan as an evaluation set, redacted? Dan and Nora both say it's you or Raj. Nothing moves until this is answered.
6. Should the output also serve the checker, and Raj's team on high-risk files, or only the analyst?
7. Is there written guidance for analysts on which clause applies where? If not, is producing it part of this work?
8. Who in your team configured the vendor's risk weightings? Raj says he wasn't involved, so it sits with you. (Low priority: the MCP server returns the score.)
9. Who owns the agent day to day after handover: the prompts, the evaluations, and changes when policy changes?
10. ACRA: there's no registry integration (Ben). Is it acceptable for the agent to flag stale registry extracts and leave the pull to the analyst? Ben says that's for whoever owns the review requirements.

### Victor Ong (Grace's manager, budget owner) — not yet interviewed

1. ★ What does the POC need to show for you to fund the next phase, and who else needs to see it?
2. ★ Is there a budget for this? Should the case be framed as cost per review, analyst productivity, or regulatory risk? (Deferred by Grace and Anna.)
3. ★ Will you sponsor the model approval track (Ben, Security, Model risk, Vendor Management) so it runs alongside the POC rather than after it?
4. Who are the right contacts in Security / Infosec, Model risk and Legal?
5. Can you help get our order form through Legal? It's holding up everything beyond the POC.

### Security / Infosec — mostly resolved

Ben says there is no separate security reviewer: his team does the sign-off, and a new model goes through the change control board (alternate Thursdays). Two items still point at an Infosec function Leo mentioned:

1. ★ Infosec ruled out prompt logging at Helios. Does the same rule apply to our harness's own audit log inside the bank's environment? Ben says that log becomes a change control item, so this needs settling before the paper goes in.
2. What guardrails do they expect in the harness, since Helios has none?

### Model risk — contact to be named

1. ★ Does an AI tool that supports KYC reviews, without making decisions, fall under model risk governance?
2. ★ What documentation and validation do you need before a POC, and before production?
3. Would you approve the evaluation set and pass criteria up front?

### Legal — contact to be named

1. ★ Status of our order form and what's holding it up. (Anna says production access waits on it.)
2. Does the current letter cover a sandbox inside the bank's GCP boundary, or only redacted samples? (Ben says yes; worth confirming on paper.)

Residency is no longer a Legal question: Raj confirmed it's internal policy VGB-DC-07.

### Data Office — contact to be named (new, from VGB-DC-07)

1. ★ Will the masked customer view be classified C2 (3.4)? That decides whether the POC can run without a data exception.
2. ★ Who signs the exception for C1 data, and what does it need? Ben couldn't say; the policy points here.
3. Is Claude via Vertex `asia-southeast1` inside the approved boundary (3.1), or a new outsourcing arrangement needing their sign-off (5.2)?

### Nora (Senior KYC analyst) — follow-up done; remaining items

Answered: she keeps no overturn spreadsheet (Sam was wrong); overturns sit in Castellan as a second event on the case, and Dan has the numbers. Guidance is the policy wording plus a training deck with examples, mostly learned by watching seniors. She'd accept a pre-submit check that confirms the file has the right documents, but not one that tells her the outcome; the gate itself is Grace's call. She shared an ownership-mismatch case, VGB-C-088410. What would prove the concept to her: pulling out the things that take time (the right document among eleven, document age against 90 days, a change of control), not a draft rationale.

1. Can we have the training deck? It's the closest thing to written clause guidance.
2. She'll review the agent's evidence extraction, clauses and screening calls against a real file, not draft rationales. Agree the format with her before the demo.
3. Who ran the auto-rationale pilot on the floor side? Dan has no QA data from it and points back to Nora's team.

### Sam (KYC analyst) — follow-up

1. Would you be willing to trial the check on your live queue once we have a prototype?
2. Can we use PR-88214 and PR-88301, redacted, as test cases?

### Anna Cruz (Vendor Management) — low priority

1. Once Ben approves the technical side, what paperwork does Vendor Management need to onboard a model vendor, and roughly how long does it take? (She said she'd check.)
2. When does the incumbent vendor's contract come up for renewal? That's the date our cost comparison has to be ready by.
3. Ben says the vendor line and GCP commitment question is yours, not his. You said it was his. Who actually owns it, and can we get the two of you in one conversation?

### Open items we owe

1. Cost per review in USD, as a range with assumptions, for Anna.
2. Productivity and regulatory case for Grace and Victor.
3. Check which Claude models have regional endpoints in `asia-southeast1` today.
4. Nora's session date was 16 September. If Sam's was the same week, his employer letter (5 June) was about 100 days old, past the 90-day rule. Confirm Sam's session date.
5. Get the sandbox and consumer forms submitted now. Ben says about a week once they're in, and nothing has gone in yet.
6. Draft the change control paper for Claude with Ben, ready for the first Thursday after Grace and Victor agree the plan.
