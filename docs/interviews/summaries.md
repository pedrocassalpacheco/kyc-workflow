Each summary is written automatically and can miss a detail, so check it against the transcript.

Conversation with Grace Lim
Grace agreed that scope and stakeholders for this engagement are not yet settled, named who the FDE should speak with next, and described the KYC review cycle and backlog pressure while deferring process/time detail to Nora.

Grace agreed the FDE's assessment was fair: "We haven't agreed among ourselves what this thing actually is yet, that's on us, not you."
Grace's stated want: "backlog gone before MAS comes back, and my analysts checking work instead of assembling files."
Stakeholders named, no fixed order: Raj (compliance requirements), Nora (floor work), Dan (QA), Ben's side (system capability), Anna (cost).
Grace said she owns this day to day; budget and the bigger call go through Victor, her boss, once she has something to show him.
Grace: "the backlog is the thing that'll get me fired if it isn't down before the next visit"; agreed it also puts the bank's growth plans under MAS scrutiny, not just her job.
KYC cycle per Grace: low risk every 36 months, medium every 24 months, high every 12 months; all accounts are reviewed, not risk-selected; roughly mid-eighties percent come out low or medium risk.
Review process per Grace: analyst opens case in the case tool, gathers documents, transaction pattern, screening results, decides if the risk rating holds, writes a rationale, closes it; a second analyst checks it; high risk also goes through Raj's team.
Grace said she could not break down where analyst time goes; the thirty-eight minutes in her deck is the vendor's time-and-motion figure, a couple of years old; Nora would know where the time goes.
Conversation with Raj Menon
Raj said the MAS finding was about evidence quality, not backlog speed: closing rationales did not consistently name the clause relied on so decisions could not always be reconstructed, and he described what a complete review record and sign-off chain must contain.

Raj said: "the letter said closing rationales didn't consistently name the clause relied on, so a decision couldn't always be reconstructed," and that slower reviews with clean evidence would still have failed the finding.
Raj said routine reviews are not sent to MAS; MAS only sees them when they inspect and pull a sample, "which is what happened last time, sixty files."
Raj said evidence should exist for every file whether or not MAS ever looks at it, since he does not know which files will be pulled next.
Raj described the record: "clause, what you looked at, what you found, names," with the analyst and checker signing off on low/medium, and his team reviewing high risk files before the rating is confirmed.
Raj clarified sign-off in Castellan means someone puts their name to the decision before it closes, separate from internal audit.
Raj said the analyst decides whether the customer's rating holds, changes, or needs more information, and MAS later checks whether that decision was reasonable and evidenced.
Raj said the hardest cases on his desk are ownership mismatches or structure changes where it is unclear if the change is material enough to re-rate.
Raj said "a human decides, always" on risk rating, and that the vendor tool suggests a score and rating that "nobody really uses."
Conversation with Nora
Nora walked the FDE through one full periodic review (Madam Tan) in Castellan from identity tab to submission, giving real document, screening, source-of-funds and ownership steps, actual time spent, and how clause citation and QA re-performance work, using Sam's recently overturned file as a comparison.

Nora walked the FDE through a full periodic review in Castellan for a customer she called Madam Tan, tab by tab: identity, documents, screening, source of funds, ownership, rationale, checklist.
Documents: the branch uploaded a lawyer's completion account for a $388,000 flat-sale credit, dated 24 July; Nora said the 90-day rule made it valid on day 53 of the review.
Screening: an overnight run flagged three namesakes; Nora said she writes "today's reason in today's words" for each rather than using the one-click button to accept last year's answers.
Source of funds: an alert fired because this year's credits were more than five times declared income; Nora matched the $388,000 credit to the completion account and the rest to salary from the new company.
Rationale: Nora said she types clause numbers "every time" (5.4, 6.5, 6.6, 8.4 on this file) even though the field says optional, because of this year's regulator letter about files that never named the clause relied on.
Time: Nora logged "an hour and nineteen minutes" of hands-on work on this file over 13 calendar days, 7 waiting on the branch; she contrasted this with Sam's file, closed in "fourteen minutes," which cited only payslips, pasted the vendor AI panel's text, and named no clause.
QA, Nora said, "pulls about one in ten" closed files and redoes them from scratch without asking her anything; she said she is sitting with Sam to redo his overturned file, PR-88214.
The FDE asked to take the documents as examples; Nora said she could not send them out and suggested asking Grace about setting up sample or test files.
Conversation with Raj Menon
Raj said the scoring model and its mechanics sit with the vendor and Grace's team, not his, and that whichever system closes a file must still have a named person accountable with reasoning that can be reconstructed. He said the overlay-versus-replace decision for the current tool belongs to Grace and vendor management, not to him.

Raj said the scoring model is 'the vendor's module, sits on Grace's side of the house' and his team only sees the rating once it's confirmed.
Raj said he does not touch scoring mechanics and that questions on how the score is calculated should go to Grace's systems team or the vendor.
Raj said he has no name for who runs the vendor module day to day and suggested asking Grace who at the vendor to speak to.
Raj said the decision on whether the solution overlays or replaces the current tool is owned by 'Grace and vendor management'.
Raj said it doesn't matter to him which approach is used 'so long as whatever closes a file still has a named person accountable and the reasoning is there for us to reconstruct'.
Conversation with Dan Koh
Dan Koh (QA/checker side) walked the FDE through how reviews move from analyst to QA, described QA's sampling and overturn process, and said he cannot hand over case files or sample data himself, pointing the FDE to Grace, Raj, Nora or Sam for those pieces.

Dan: case gets opened in Castellan when the review falls due or something trips it, analyst works it, checker signs, then it lands with QA for sampling.
Dan: review schedule is low/standard every 36 months, elevated/medium every 24, high risk every 12; ownership change or a screening hit can also trigger one early.
Dan: QA pulls about one in ten of closed reviews at random, not just where the rating moved, and about one in seven comes back overturned.
Dan listed hard failure items: missing evidence date on a source of funds check, ownership check not actually done, a screening hit left without a reason, or no named analyst and timestamp on the close.
Dan: dates, named analyst, timestamp, and an undispositioned screening hit are easy, 'a machine can catch a blank field'; whether the source of funds explanation is plausible or the ownership change read correctly is judgment, 'that's where our checkers earn their pay'.
Dan: QA works off 'this is the list we work off, version seven'; the analyst side has its own six-item list, with one item added last month about checking generated text against the customer.
Dan: re-performing a low takes about 25 minutes for a checker; he does not track how long the original analyst takes and said to ask Nora or Sam.
Dan said pulling a sample of strong and overturned files is 'not mine to hand over on my own', there would need to be a basis for pulling case data, and pointed the FDE to Grace or Raj.
Conversation with Ben Tan
Ben Tan (platform engineering) walked the FDE through VGB's systems architecture and governance constraints: five MCP servers already front the core systems and feed Helios, Helios is the only sanctioned path to any model, masked-data access needs a paper exception, and an earlier auto-rationale pilot was tried and shelved; several specifics (model allowlist, region failover, RBAC/service-account detail for a new consumer) were deferred to Leo.

Five internal MCP servers already built, one per system (case history/Castellan, customer master, screening, doc store, transaction summary), read-mostly, feeding Helios as context; nothing writes back into Castellan.
Helios is 'the only sanctioned path, full stop'; it fronts Vertex, Singapore region, with logging and redaction on the way through; the model itself lives Google-side.
Ben said the harness calls the MCP servers direct since they're internal, with no need to go via Helios; Helios is only in the path when calling the model itself.
A masked customer view 'might count as lower classification'; otherwise accessing customer-identifying data is an exception, and 'exceptions here are paper,' taking weeks.
Ben said customer-identifying data stays inside VGB's GCP boundary per their classification policy, but was not sure whether that is MAS law or an internal choice, and pointed to Raj or legal for that.
Authentication to the MCP servers is via scoped service accounts; RBAC exists on the servers; exact setup for a new consumer like the harness is Leo's to provision.
Ben's condition: 'if my team can't run it without you, we won't take it'; anything behind Helios goes through change control on alternate Thursdays.
Ben described an earlier auto-rationale model piloted on an earlier version of Helios about eighteen months ago, with one of the floor teams for six weeks: rationales came out generic, QA overturns went up, and it was quietly shelved.
Conversation with Leo
Leo (who runs Helios day to day) walked the FDE through the only sanctioned model path (Vertex Gemini in Singapore, no Claude, no embeddings), how new consumers and service accounts get provisioned, and confirmed that analyst identity, redaction, and audit logging are all unresolved or limited; the FDE's statement that they work for Anthropic surfaced a mismatch with Helios's Vertex-only path.

Leo said Helios only fronts Vertex AI in Singapore, running whatever Gemini model is current there, with no Claude, no OpenAI, and no embedding models on the allowed list.
Leo said tool calling on Helios uses the older schema, not the newer parallel tool-use, so anything built has to work around that.
Leo said adding a new model goes through Ben and security review, not just him, and he'd need to check the gateway config for exact version strings.
FDE said 'I work for anthropic' and Leo said that would be a problem since Helios only supports Gemini models on this path, and that a Claude option on Vertex model garden would be a Ben and procurement conversation.
Leo said if Vertex Singapore is degraded, calls just fail with no fallback region configured, pinned to Singapore for data residency, and he hasn't seen it go down but wouldn't swear to the SLA.
Leo said setting up a new consumer needs a security form, a provisioned service account, and scopes set per MCP server, taking about a week once the form is in.
Leo said the service account would be scoped to the agent broadly across the MCP servers, not narrowed per analyst, so the analyst's identity rides along as data in the call rather than a separate access boundary; this scoping question hasn't been settled.
Leo said Helios doesn't redact content itself, only logs metadata, and that the masked customer view upstream does strip names and related-party fields, which is what affected the earlier pilot.
Leo said Helios logs are metadata only (caller, timestamp, model, token counts, latency, request id), kept ninety days, with no prompt or response text, so the logs can't be used to audit content.
Conversation with Leo
Leo said that approving a new model for security goes through Ben and then a security review, but could not name a specific contact.

FDE asked who on infosec or security should be contacted to approve a new model.
Leo said 'that's not really me, that goes through Ben and then security review on top.'
Leo said he didn't have a name off the top of his head for who handles it on the security side.
Leo said Ben would know who picks it up on their side.
Conversation with Anna Cruz
Anna said she has no fixed cost ceiling but needs an all-in cost per review from the FDE to compare against the incumbent vendor's 2.40, and that the engagement's order form is still with Legal so production access waits on it while sandbox and redacted samples are fine under the current letter.

Anna said she needs "an all-in cost per review I can put next to the vendor's 2.40," adding "a range with assumptions is fine."
Anna said budget "sits with Victor and Grace's side, not vendor management," and that she hasn't seen a budget line for this.
Anna said "the paper for this engagement itself isn't done yet, your order form's still with Legal, so production access waits on that," but "sandbox and the redacted samples are fine on the letter we have."
Anna said the question of cloud commitment versus a new vendor approval is "more Ben's side."
Anna said "whether it's worthwhile is Victor's call once he sees both" figures.
Anna said budget proposals should go "through Grace, really, she's your sponsor," and that she only compares numbers, not approves spend.
Anna said onboarding a model vendor "would be new for us" and "I'd have to check what the process actually looks like."
Conversation with Anna Cruz
Anna asked the FDE for a USD cost-per-review figure to set against the incumbent vendor's benchmark of USD 2.40 per review, and the FDE agreed to split the work into a cost-per-review range for Anna and a separate productivity case for Grace and Victor, while noting that production access is still waiting on the order form.

Anna asked for 'a number' in the same shape as the vendor benchmark: dollars per review.
Anna said the USD 2.40 figure is 'the vendor's incumbent price, all in with their AI assist panel' and does not include analyst salary.
Anna said she needs 'a cost per review, your model cost plus whatever it costs VGB to run it, all in' and that 'a range with assumptions is fine.'
FDE proposed two separate deliverables: a USD cost-per-review range for Anna, and a separate productivity case on analyst time and QA rework for Grace and Victor.
FDE said the order form is still with Legal, that the sandbox and redacted samples are covered by the existing letter, and that production access needs the order form signed.
Anna said to 'put the range in the plan Grace takes to Victor,' which she will use 'when renewal comes round.'
Conversation with Sam
Sam walked the FDE through a live high-risk review (PR-88301) and described how reviews actually get worked: where time goes, which clauses give trouble, and how the Assist panel gets used despite most of the floor having turned it off.

Sam starts from whatever Castellan next in queue, checks customer master for changes, then transaction summary, then screening; trusts a sighted original document over a payslip the customer emailed in.
Sam said the system flags turnover mismatches under clause 4.7(b) and he then files an RFI to the branch to chase the customer.
Sam said a low review takes him 'maybe fifty, fifty-five minutes, which I think is slow,' and that 'Nora does one in half an hour.'
Sam said clauses 5.4 (source of funds) and 6.6 (ownership) are the ones he 'never feel sure I've read ... right,' and that when the clause field says optional 'I leave it blank.'
Walking PR-88301, Sam used the Assist panel for the 5.4 write-up, saying 'don't tell Nora but I use the assist thing for the write-up,' then changed 'a couple of words so it reads like me.'
Sam closed PR-88301 in 'thirty-eight minutes, which is fast for a high,' and said most of that time is waiting for Castellan to load PDFs.
Sam said QA feedback is 'usually a line or two in the checklist' and that his files 'come back more than most'; he said Nora 'keeps a spreadsheet of every overturn.'
Asked what tool he'd want, Sam said he'd rather have something that 'stops me before I hit submit' than a drafted rationale, and said the choice 'is more a Grace or Nora question.'
Conversation with Ben Tan
Ben answered what he could on Helios, change control and sandbox access, but deferred most technical detail (redaction, identity, masked view contents, pilot failure, prompt-change rules) to Leo, Anna or Security, and said the data exception and new-model approval both run through formal processes he does not own.

Ben said he probably meant metadata logging, not content redaction, when he described Helios, and would check with Leo.
Ben said vendor line and commitment for adding a new model is Anna's call, not his.
Ben said any new model behind Helios goes through change control, with the board sitting alternate Thursdays, and he can't add something to the docket without a case behind it.
Ben said his team does the security sign-off itself, there's no separate security person to send the FDE to.
Ben's instinct on identity is a service account with the analyst ID logged alongside, but said 'don't quote me' and deferred to Leo.
Ben said the data exception for unmasked customer data takes 'weeks to months,' and he'd have to check who signs it.
Ben said he didn't know that missing related-party fields in the masked view was what tripped up the old pilot, and isn't sure what the masked view contains at that level.
Ben said sandbox access is covered under the current letter and would sit inside VGB's GCP project reaching the MCP servers, but the form hasn't gone in yet, about a week once it does.
Conversation with Ben Tan
Ben clarified change-control submission requirements, confirmed VGB has no separate failover region for Vertex Singapore, said the risk-scoring formula belongs to the vendor, outlined what his team would need to run this without the FDE, and described the earlier pilot as informally shelved after overturns rose.

Ben said a change-control submission needs 'a paper on it, basically a case, what's changing and why,' going to the board on alternate Thursdays; whether a prompt change needs its own submission he was not sure, calling it 'a Leo question.'
On Vertex Singapore SLA and failover, Ben said 'we don't have a separate failover region for this. If it drops, it drops, and you retry,' and said SLA numbers are 'really the GCP account rep, not us.'
On the risk scoring formula, Ben said his team 'runs the vendor module' but 'we don't own the formula or the weightings,' and that 'nobody's shown me those written down on our side.'
For his team to run this without the FDE, Ben said they need runbook and monitoring, someone on their side who understands the harness (not just a dashboard), and that on-call 'sits with my team either way, we don't push that out'; he said evaluation harness is 'new territory' and he'd need to see it first.
On the audit trail, Ben said Helios 'won't give you that, it's metadata only, that's deliberate,' and that if reasoning needs keeping, the harness must log it itself inside the environment, which then 'becomes something change control looks at too.'
On the earlier pilot, Ben said there was no formal retrospective, it was 'mostly a conversation,' that 'Nora's team pushed back, overturns went up, we just quietly stopped,' and that Nora would be the one with any notes.
Conversation with Raj Menon
Raj set his conditions for any AI-assisted closure: a named person must sign every file, nothing closes on its own, evidence has to be reconstructable, and QA must sign off before anything goes near production; he also said the Singapore data boundary is VGB's own board-approved classification policy, not an MAS rule.

Raj: "What I would not accept is anything closing a file on its own. Low risk or not, someone signs, every time."
Raj said rollout would be stopped by: no named person accountable for a closure, evidence he can't reconstruct per file, or QA not brought in and signed off on the approach.
POL-042 version 4.2 is current; the text will be in the data pack from Ben's team; Raj would rather not hand out his own copy and wants ambiguous clauses brought to him to go through the wording together.
Raj: the Singapore boundary is VGB's own classification policy (data on sanctioned paths must stay inside the Google Cloud boundary in Singapore, board approved), not an MAS rule; MAS cares about outsourcing controls and notification, not the cloud brand, so a different vendor region 'wouldn't automatically fail with them. But it would fail with us.'
Raj: closing a high-risk file with a source-of-funds RFI outstanding 'shouldn't be confirmed, RM pressure or not'; if that happened on Sam's case, 'that's something QA or I need to look at directly.'
Raj wants ownership changes, stale documents, and screening carry-forwards in the evaluation set, but has no count on which category overturns most ('nobody's actually counted').
Raj: the risk scoring weightings are in the vendor module on Grace's side; he wasn't involved in configuring them. High-risk files need the same evidence content as others plus his team's sign-off before the rating is confirmed.
Conversation with Grace Lim
Grace set POC scope to low and medium reviews, deferred the rationale/evidence-pack format and checker ownership to Raj, pointed test-case access to Ben, and said she wants a named owner for the agent after handover before it goes anywhere.

Grace said she doesn't mind evidence pack vs drafted rationale, "as long as it's fast for them and Raj is happy with it... that's Raj's call."
Grace agreed to push for a clean check report being a hard stop: "Yes, that I'd push for. If it's not a hard stop people will skip it when they're busy."
Grace said the backlog is "about forty seven thousand" and MAS is back in twelve months, "that's the number I live with."
Grace said total reviews are "about three hundred and thirty thousand reviews a year," with "eighty-four percent of those are low or medium," exact count split not known.
Grace set POC scope: "Start with low and medium, that's most of the backlog and where I need movement," highs optional and "don't let that hold up the rest."
Grace said redacted/synthetic test cases are "Ben's side, he controls what gets pulled and in what shape," said to ask him directly first.
Grace said there's a training deck but "nobody's written out clause by clause what applies where" and she "won't say no" to that being built as part of the work.
Grace said she doesn't know who configured the vendor's risk weightings ("that'll be from years back, before my time") and thinks Anna would know who signed off.
Conversation with Nora
Nora walked the FDE through a full periodic review in Castellan (Madam Tan), showing where the actual time goes, and said she would accept a pre-submit document-completeness check but not anything that recommends the outcome.

Nora said she keeps no overturn log ("I don't keep anything like that"); overturns show as a second event in Castellan and Dan in QA samples about one in ten closed files and re-performs them.
Nora said she would accept a pre-submit check if it only confirms the file has the right documents, but "if it tries to tell me the outcome, I'm not using it."
On Madam Tan's file, Nora cleared three watchlist name matches as not her, matched a $388,000 credit to a lawyer's completion account dated within the 90-day rule (day 53 of 90), and recorded a change of control to 70/30 ownership with her son, pulling a fresh registry extract for $5.50.
Nora said time on that case was "an hour and nineteen minutes of actual work, spread over thirteen days on the calendar," seven of them waiting on a document from the branch.
Nora contrasted this with Sam's case, closed in fourteen minutes using the vendor AI panel's pasted paragraph and no clause, which QA sent back; Sam is five months in and the queue wants forty files a week from him.
Nora said the hard part is finding and checking things, the completion account, the 90-day math, the change of control, not writing the rationale sentence, and said she'd want an agent to surface those "with the dates."
When the FDE offered to mock up the agent's output on a case Nora had already flagged, Nora said it would "prove nothing I didn't know" since it skips the work of finding and verifying things.
Conversation with Dan Koh
Dan described how QA actually samples and scores files (checklist pass/fail, roughly one in ten per month, unchanged since the MAS letter) and said that pulling an evaluation set or case data is a decision for Grace or Raj, not him.

Dan said QA does not break failures down by category or analyst: 'It's pass or fail against the checklist, item by item.'
Dan said common failures are 'missing evidence date, ownership check not done, a screening hit closed without a reason.'
Dan described a passing rationale as one that 'names the clause, has the evidence date, and the screening hit is dispositioned with a reason,' and a fail as 'a conclusion with no clause cited, or the date's missing.'
Dan said he cannot hand over or pull case files or an evaluation set himself: 'that's Grace or Raj's call on the data side.'
Dan said if he could re-perform off a check report it 'saves my checkers time,' but he would still want 'sampled re-performance, overturn rate at or below what we see now, and a named person taking ownership of the file.'
Dan said he does not know the 90-day rule number off the top of his head; he checks that 'the evidence date is there and makes sense for the review' under 5.4.
On Sam's reported claim about a high-risk file closed with an RFI open, Dan said 'First I'm hearing that one,' and that 'a high shouldn't close with an RFI still open,' which needs to go through Raj's side.
Dan said sampling is 'random, roughly one in ten of what's closed that month, same as before the letter,' and that the MAS letter was about rationale quality, not sampling rate.