1. What you will build first
Start with one sentence that your main contact could repeat to senior managers. Then say what the MVP does and who uses it.

We are building an AI-supported workflow that prepares the evidence before an analyst opens a low or medium-risk KYC review and checks the file before it is submitted, so analysts spend their time deciding and signing, not hunting through documents, and every closed file names its clause.

What it does: a read-only, source-cited evidence pack before the review, and a pre-submit check for missing clauses, stale or customer-supplied documents, unaddressed screening hits, ownership changes without a registry extract, and open RFIs. A clean check report is a condition of the checker accepting the file, a process rule Grace enforces, since Castellan cannot be changed this year, so it is not skipped under pressure.

Who uses it: analysts on low and medium reviews, 84% of the backlog. Checkers and QA re-perform from the check report. Compliance gets clause, check, finding and names on every file. A named analyst still decides and signs.

This is not an agent. Following Anthropic's guidance to use the simplest design that works, the steps run in a fixed order and Claude only reads and compares. It does not choose its path, call systems on its own, or decide when a review is done.

2. What you will leave out, and why
List the stakeholder requests that you will not build, and give a short reason for each.

High-risk files. Deferred. Grace asked us to start with low and medium, most of the backlog. Highs need the same evidence plus Compliance sign-off and extend the workflow once QA signs off the approach.

Fresh registry checks. Not automated. There is no registry integration, so analysts keep pulling a fresh profile from inside Castellan. The workflow only flags when the extract on file is out of date.

Write-back to Castellan. Excluded this year. A write interface is a vendor change request taking months, so the analyst attaches the check report to the case, which makes it part of the record.

Autonomous decisions and auto-written rationales. Excluded. Both earlier attempts produced generic paragraphs: the Helios pilot raised QA overturns and was shelved, and the floor switched off the vendor panel behind PR-88214's overturn. A named analyst makes every decision, edits the rationale and signs.

Full resilience. Excluded. Claude is reachable only through Helios to Vertex in Singapore, and the bank's data policy keeps customer data in that region. With no failover it fails and retries, as Helios does today, and the analyst works by hand meanwhile. A second region is a Board matter.

3. How you will test that it works
Say how many cases you will test, how you choose them, and which result would tell you that the MVP is not good enough.

Test set: 60 closed low and medium reviews, the sample size MAS used, pulled from Castellan and redacted under Grace's or Raj's authority. 30 that passed QA, random from the last six months, to show no false alarms on clean files. 20 that QA overturned, covering ownership changes, stale documents, screening carry-forwards and customer-supplied evidence, including PR-88214 and VGB-C-088410. 10 constructed cases for rare situations and attempts to make the workflow rate, close or write to a file. Sam's PR-88301 is a 61st case: high risk, submitted with an RFI open, not yet through QA, so it only exercises the check.

Judging: Dan's checkers re-perform each case from the pack and check report, blind to the original outcome. Nora checks the packs against the source documents.

The MVP fails if the QA overturn rate on tool-assisted files is above today's, roughly one in seven; if the check misses the recorded overturn reason on more than 2 of 20; if any statement in a pack cannot be traced to a document; if the workflow rates, writes a rationale or acts on a file in any constructed case; or if Nora or Dan would not use it on a live queue. Time saved is measured, not a pass condition.

4. What one review will cost to process
Estimate what processing one review with your MVP will cost and say what the estimate includes and leaves out. Compare it, per review and per year at the client's volume, with what a review costs the client today: what it pays its vendor and what it costs in a person's time.

The MVP costs an extra USD 0.40 to 1.20 per review (USD 110k to 330k a year) in model and infrastructure fees, but saves USD 10 to 20 per review (USD 2.8M to 5.5M a year) in analyst and QA time. MVP figures are at low and medium volume, about 277,000 reviews a year, where it runs.

Today, across all 330,000 reviews: USD 2.40 per review for vendor software (about USD 792k a year) plus about 90 minutes of person time per review, analyst plus checker (about USD 60 per review, about USD 20M a year), built from Nora's 79 minutes on a medium, Sam's 50 to 55 on a low, and about 25 minutes for the checker.

Net impact: on low and medium reviews, roughly USD 2.5M to 5.4M a year, rising if highs are added later.

Includes: Singapore endpoint model tokens for the evidence pack and the check, Google's 10% regional premium, and hosting and operating the workflow inside the bank. Excludes: the vendor's risk-scoring module, which keeps running, and implementation and engagement fees. Person time assumes USD 40 per loaded hour, to be replaced with Grace's HR figure. The 15 to 30 minute saving will be measured during the POC, not assumed.

5. Who will run the MVP after you leave
Name who will operate the MVP each day and who acts when a result is wrong. Say what you hand over so that they can run it without you.

Day to day: Ben's platform team runs it, which was his condition for taking it. On-call stays with them, the workflow sits behind Helios under their change control, and one named engineer, most likely Leo, understands the harness rather than watching a dashboard. A named senior analyst on Grace's floor, Nora the obvious candidate, owns what the workflow checks: the clause guide, the evaluation set, and changes when POL-042 changes or QA finds a new failure pattern.

When a result is wrong: the analyst overrides it on the file, since nothing the workflow produces is binding. The floor owner logs the case and decides whether a rule or prompt changes. Raj approves rule changes, Dan re-runs the evaluation set before they go live, and Ben's team deploys through change control.

Handover: the sandbox harness, the 60-case evaluation set with results, the audit log design, monitoring and runbooks for Ben's team, training for the named engineer, a clause-to-situation guide for the floor, and the cost figures.

6. What you need from the client before you start
List the data, access, approvals and decisions that you need, and who can give each one.

Data: POL-042 v4.2 text and masked view field list (Ben). 60 redacted closed reviews, 30 passed, 20 overturned, 10 constructed (Grace or Raj authorise, Ben extracts). Training deck (Nora). Today's overturn rate (Dan).

Access: a sandbox in the bank's Google Cloud project and a service account with read scopes on the five MCP servers, a week after the forms go in (Ben, Leo).

Approvals: change board approval for Claude Sonnet 4.6, the newest Claude served single-region, on the Singapore endpoint via Helios, by paper before the four weeks start (Ben writes, Grace sponsors, Victor informed; not interviewed, to confirm). Anthropic as model vendor (Anna). Masked view as C2 or a C1 exception (Data Office). Whether Claude on Vertex Singapore is outsourcing under VGB-DC-07 (Raj). Infosec view on the audit log (Ben). Order form (Anna, Legal).

Decisions: evidence pack plus check as artifact, drafted text deferred (Grace, Raj). Clean check report as a condition of checker acceptance (Grace; Raj confirms it is record). The 90-day rule and whether payslips are independent evidence (Raj, Dan). Two owners after handover (Ben, Grace). What the demo must show to fund the next phase (Victor).

7. What you ask the client to approve
Write one or two sentences, for example a request to approve a four week pilot for one group of users.

Please approve a four-week proof of concept in the bank's sandbox, in which Nora's team and Dan's checkers test the AI-supported workflow on 60 redacted low and medium-risk reviews, judged on QA's overturn rate. The four weeks start once the sandbox, the evaluation set and the change board approval for Claude behind Helios are in place, so we also ask for authorisation to pull the evaluation set, sponsorship of the change control paper now, and the naming of the two people who will own the workflow after handover.

FOR THE ANTHROPIC TEAM - 
For the record: the workshop said we could return to the interviews multiple times, but by the time my other questions were answered a threshold was reached and I was unable to interview Victor. Items attributed to Victor in sections 5 to 7 are therefore inferred from what Grace and Anna said about him, not from Victor himself.
