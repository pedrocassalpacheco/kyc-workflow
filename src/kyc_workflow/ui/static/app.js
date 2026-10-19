/* VGB records UI. Plain JavaScript, no build step. */
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (n) => (n ?? 0).toLocaleString();

  // ---- views ------------------------------------------------------------------
  document.querySelectorAll(".navbtn").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".navbtn").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
    if (b.dataset.view === "evals") loadHistory();
  }));

  // ---- tiny markdown: bold, inline code, bullets, pipe tables, paragraphs ---------
  function md(text) {
    const lines = String(text).split("\n");
    let html = "", i = 0;
    const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    while (i < lines.length) {
      const l = lines[i];
      if (/^\s*\|.*\|\s*$/.test(l)) {
        const rows = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
        const cells = (r) => r.trim().slice(1, -1).split("|").map((c) => c.trim());
        const body = rows.filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r));
        html += "<table>" + body.map((r, k) => "<tr>" + cells(r).map((c) => (k === 0 ? "<th>" : "<td>") + inline(c) + (k === 0 ? "</th>" : "</td>")).join("") + "</tr>").join("") + "</table>";
        continue;
      }
      if (/^\s*[-*] /.test(l)) {
        html += "<ul>";
        while (i < lines.length && /^\s*[-*] /.test(lines[i])) { html += "<li>" + inline(lines[i].replace(/^\s*[-*] /, "")) + "</li>"; i++; }
        html += "</ul>";
        continue;
      }
      if (l.trim() === "") { i++; continue; }
      let p = [];
      while (i < lines.length && lines[i].trim() !== "" && !/^\s*[-*] /.test(lines[i]) && !/^\s*\|.*\|\s*$/.test(lines[i])) { p.push(lines[i]); i++; }
      html += "<p>" + inline(p.join(" ")) + "</p>";
    }
    return html;
  }

  // ---- chat -------------------------------------------------------------------
  const messages = $("messages");
  function addMsg(role, text, cls = "", turnline = "") {
    const d = document.createElement("div");
    d.className = `msg ${role} ${cls}`.trim();
    d.innerHTML = role === "user" ? esc(text) : md(text) + (turnline ? `<span class="turnline">${esc(turnline)}</span>` : "");
    messages.appendChild(d);
    messages.scrollTop = messages.scrollHeight;
    return d;
  }
  let examples = [];
  function paintExamples() {
    const el = $("examples");
    if (!examples.length || messages.children.length) { el.innerHTML = ""; return; }
    el.innerHTML = `<span class="lead">Try one of these, or ask your own. The assistant reads the records and cites them; it does not rate, decide, close or draft.</span>` +
      examples.map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
    el.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { $("chat-input").value = c.textContent; $("chat-input").focus(); }));
  }
  async function loadChat() {
    const h = await (await fetch("/api/chat/history")).json();
    messages.innerHTML = "";
    h.messages.forEach((m) => addMsg(m.role, m.text, m.withheld ? "withheld" : m.refused ? "refused" : ""));
    paintExamples();
  }
  $("chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("chat-input"), text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    paintExamples();
    const pending = addMsg("assistant", "…", "pending");
    $("chat-send").disabled = true;
    try {
      const r = await fetch("/api/chat/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
      const d = await r.json();
      pending.remove();
      if (!r.ok) { addMsg("assistant", `error: ${d.error}`, "refused"); return; }
      const t = d.turn;
      addMsg("assistant", d.reply, t.outcome === "withheld" ? "withheld" : t.outcome === "refused" ? "refused" : "",
        `turn ${t.turn} ${t.outcome} · ${t.model_calls} model call(s) · ${t.tool_calls} tool call(s) · in ${fmt(t.input_tokens)} out ${fmt(t.output_tokens)} · ${Math.round(t.duration_ms)} ms`);
    } catch (err) {
      pending.remove(); addMsg("assistant", `request failed: ${err}`, "refused");
    } finally { $("chat-send").disabled = false; input.focus(); }
  });
  $("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); } });
  $("chat-new").addEventListener("click", async () => {
    const r = await fetch("/api/chat/new", { method: "POST" });
    if (r.ok) { messages.innerHTML = ""; resetCosts(); refreshStatus(); paintExamples(); }
  });

  // ---- workflow --------------------------------------------------------------
  // The fixed workflow, as the analyst sees it: five phases, twelve steps, who does what.
  const PHASES = [
    { title: "Load", who: "code", steps: [["load_case", "Pull the review, record, accounts, owners, screening, cases, documents and transactions through the MCP server"]] },
    { title: "Count", who: "code", steps: [
      ["transactions", "Turnover vs declared, monthly swings, markets, Group 3, cash band, pass-through"],
      ["screening", "Bands, undispositioned hits, eliminations outside §8.4, unscreened owners"],
      ["history", "Open and lapsed RFIs, prior outcomes and alerts"]] },
    { title: "Read", who: "Claude", steps: [["documents", "Each document into issuer, date, subject, amounts, facts, owners; code adds age and independence"]] },
    { title: "Compare", who: "Claude + code", steps: [
      ["consistency", "Document substance against the record (§4.7(d), §4.5(c), §4.4(e))"],
      ["ownership", "Registry extract against owners and officers on record (§6.5, §6.6)"],
      ["matching", "Each credit stream to the document that explains it (§5.4)"],
      ["plausibility", "Activity against the declared profile and the Appendix B baseline (§5.4, §7.3, §7.5)"],
      ["narratives", "Refusals or lapsed RFIs in narratives; adverse-media categories (§4.4(d), §8.7)"]] },
    { title: "Conclude", who: "Claude, then code", steps: [
      ["reviewer", "A second read of the whole file for anything the checks missed; marked not verified"],
      ["clauses", "Every §4.3 condition and §4.4, §4.5, §4.7 trigger: met, exception or not assessed"]] },
  ];
  const STEPS = PHASES.flatMap((p) => p.steps.map((s) => s[0]));
  const MODEL_STEPS = new Set(["documents", "consistency", "matching", "plausibility", "narratives", "reviewer"]);
  const DESC = Object.fromEntries(PHASES.flatMap((p) => p.steps));
  const packState = { review: null, steps: {}, tokens: { in: 0, out: 0 } };
  function paintSteps() {
    const st = (s) => packState.steps[s] || { status: "pending" };
    const done = STEPS.filter((s) => ["done", "skipped", "error"].includes(st(s).status)).length;
    const running = STEPS.filter((s) => st(s).status === "running");
    const pct = Math.round((done / STEPS.length) * 100);
    const now = running.length ? `<b>${running.join(", ")}</b> · ${running.map((s) => DESC[s]).join(" · ")}${running.some((s) => MODEL_STEPS.has(s)) ? " · <span class=\"claude\">Claude is reading</span>" : ""}`
      : done === STEPS.length ? `<b>done</b> · ${done} of ${STEPS.length} steps` : done ? `${done} of ${STEPS.length} steps done` : packState.review ? "waiting to start" : "Enter a review id and build the pack to watch the workflow run.";
    const box = (name, desc) => {
      const s = st(name);
      const res = s.status === "done" ? `${Math.round(s.duration_ms || 0)} ms${s.findings != null ? ` · ${s.findings} finding(s)` : ""}${s.exceptions ? ` · ${s.exceptions} exception(s)` : ""}`
        : s.status === "running" ? "running…" : s.status === "error" ? `error: ${esc(s.error || "")}` : s.status === "skipped" ? "skipped (model off)" : "";
      const ic = s.status === "done" ? "✓" : s.status === "running" ? "●" : s.status === "error" ? "✕" : s.status === "skipped" ? "–" : "○";
      return `<div class="pstep ${s.status}${s.exceptions ? " exc" : ""}"><div class="n"><span>${name}${MODEL_STEPS.has(name) ? ' <span class="claude">Claude</span>' : ""}</span><span class="ic">${ic}</span></div><div class="d">${esc(desc)}</div>${res ? `<div class="r">${res}</div>` : ""}</div>`;
    };
    $("pack-progress").innerHTML = `<div class="bar"><div style="width:${pct}%"></div></div><div class="now">${now}</div><div class="phases">` +
      PHASES.map((p) => `<div class="phase"><h4><span>${p.title}</span><span class="who">${p.who}</span></h4>${p.steps.map(([n, d]) => box(n, d)).join("")}</div>`).join("") + "</div>";
  }
  function openDocument(name) {
    fetch("/api/document/" + encodeURIComponent(name)).then((r) => r.json()).then((d) => {
      $("modal-title").textContent = name; $("modal-body").textContent = d.text || d.error || ""; $("modal").hidden = false;
    });
  }
  $("modal-close").addEventListener("click", () => ($("modal").hidden = true));
  $("modal").addEventListener("click", (e) => { if (e.target === $("modal")) $("modal").hidden = true; });
  function cite(c) {
    const label = [c.system, c.dataset, c.document || c.record_id, c.field].filter(Boolean).join(" / ");
    const rid = c.request_id ? ` [${c.request_id.slice(0, 8)}]` : "";
    return c.document ? `<span class="doc" data-doc="${esc(c.document)}">${esc(label)}</span>${esc(rid)}` : esc(label + rid);
  }
  function findingCard(f) {
    const who = f.origin === "model" ? '<span class="badge model">Claude read</span>' : '<span class="badge code">code</span>';
    const unv = f.verified === false ? '<span class="badge unverified">not verified</span>' : "";
    return `<div class="finding ${f.severity} ${f.kind}"><span class="fid">${esc(f.id)}</span><span class="clause">§${esc(f.clause)}</span><span class="badge kind">${esc(f.kind.replace("_", " "))}</span>${who}${unv}
      <div><b>${esc(f.title)}</b></div><div class="detail">${esc(f.detail)}</div><div class="cites">${(f.citations || []).map(cite).join("; ") || "no citation"}</div></div>`;
  }
  function renderPack(p) {
    const ex = p.findings.filter((f) => f.kind === "exception");
    const ms = p.findings.filter((f) => f.kind === "model_suggested");
    const rest = p.findings.filter((f) => ["condition_met", "information"].includes(f.kind));
    const na = p.findings.filter((f) => f.kind === "not_assessed");
    const order = { high: 0, medium: 1, low: 2, info: 3 };
    ex.sort((a, b) => order[a.severity] - order[b.severity]);
    const tx = p.transactions;
    let html = `<div class="packhead"><b>${esc(p.customer_name)}</b> (${esc(p.customer_ref)}, ${esc(p.customer_type)}) · review ${esc(p.review_id)} · period ${p.period_start} to ${p.period_end}${p.period_inferred ? " (inferred)" : ""} · tier ${p.tier ?? "?"} · model ${esc(p.model || "none")}
      ${p.scope_note ? `<div class="note">${esc(p.scope_note)}</div>` : ""}
      <div class="nodecide">This pack states what the records show against POL-042 conditions. It does not rate, decide or recommend an outcome; a named analyst does.</div>
      ${tx ? `<div class="muted" style="margin-top:6px">credits S$${fmt(Math.round(tx.credits_total))} in ${tx.credit_count} items · debits S$${fmt(Math.round(tx.debits_total))} · declared ${tx.declared_turnover ? "S$" + fmt(tx.declared_turnover) : "n/a"}${tx.turnover_ratio != null ? ` · ratio ${Math.round(tx.turnover_ratio * 100)}%` : ""}${tx.cash_share != null ? ` · cash ${Math.round(tx.cash_share * 100)}%` : ""} · ${p.request_ids.length} bank requests · ${p.model_calls.length} model calls</div>` : ""}</div>`;
    html += `<h2>Exceptions (${ex.length})</h2>` + (ex.map(findingCard).join("") || '<p class="muted">none</p>');
    html += `<h2>Clause conditions</h2><table class="condtable"><tr><th>Clause</th><th>Condition</th><th>Status</th><th>Findings</th></tr>` +
      p.conditions.map((c) => `<tr><td>§${esc(c.clause)}</td><td>${esc(c.label)}</td><td class="${c.status}">${esc(c.status.replace("_", " "))}</td><td>${c.finding_ids.join(", ") || "–"}</td></tr>`).join("") + "</table>";
    if (p.documents.length) html += `<h2>Documents read by Claude (${p.documents.length})</h2><table class="condtable"><tr><th>Document</th><th>Type</th><th>Issuer</th><th>Dated</th><th>Age</th><th>Independent</th></tr>` +
      p.documents.map((d) => `<tr><td><span class="doc" style="color:var(--series-1);cursor:pointer;text-decoration:underline" data-doc="${esc(d.stored_filename)}">${esc(d.stored_filename)}</span></td><td>${esc(d.doc_type)}</td><td>${esc(d.issuer || "?")}</td><td>${esc(d.document_date || "?")}</td><td>${d.age_days ?? "?"}</td><td>${d.independent == null ? "?" : d.independent}</td></tr>`).join("") + "</table>";
    if (p.screening.length) html += `<h2>Screening (${p.screening.length})</h2><table class="condtable"><tr><th>Hit</th><th>Subject</th><th>Category</th><th>Score</th><th>Band</th><th>Status</th><th>Issues</th></tr>` +
      p.screening.map((i) => `<tr><td>${esc(i.hit_id)}</td><td>${esc(i.subject)} (${esc(i.role)})</td><td>${esc(i.category)}${i.media_category ? " cat " + i.media_category : ""}</td><td>${i.score ?? ""}</td><td>${esc(i.band)}</td><td>${esc(i.status)}</td><td>${esc(i.issues.join("; ")) || "–"}</td></tr>`).join("") + "</table>";
    html += `<h2>Model-suggested, not verified (${ms.length})</h2><p class="muted">A second read of the whole file by Claude. Candidates for the analyst to check, not findings of the fixed checks.</p>` + (ms.map(findingCard).join("") || '<p class="muted">none</p>');
    html += `<h2>Other findings (${rest.length})</h2>` + rest.map(findingCard).join("");
    if (na.length) html += `<h2>Not assessed (${na.length})</h2>` + na.map(findingCard).join("");
    html += `<h2>Model calls (${p.model_calls.length})</h2><table class="condtable"><tr><th>Step</th><th>Purpose</th><th>Request</th><th>In</th><th>Out</th><th>ms</th></tr>` +
      p.model_calls.map((m) => `<tr><td>${esc(m.step)}</td><td>${esc(m.purpose)}</td><td>${esc(m.request_id.slice(0, 8))}</td><td>${fmt(m.input_tokens)}</td><td>${fmt(m.output_tokens)}</td><td>${Math.round(m.latency_ms)}</td></tr>`).join("") + "</table>";
    $("pack-result").innerHTML = html;
    $("pack-result").querySelectorAll(".doc").forEach((el) => el.addEventListener("click", () => openDocument(el.dataset.doc)));
    $("check-panel").hidden = false;
    $("check-outcome").value = p.recorded_outcome || "unchanged";
    $("check-clauses").value = (p.recorded_clauses || []).join(", ");
    $("check-rationale").value = p.recorded_rationale || "";
    $("check-result").innerHTML = p.recorded_outcome ? `<p class="muted">Prefilled from the write-up on file by ${esc(p.recorded_analyst || "the analyst")}.</p>` : "";
  }
  function renderCheck(c) {
    const head = c.clean ? '<p class="clean">CLEAN: no high or medium flags. The checker can accept the file from this report.</p>' : `<p><b>${c.flags.length} flag(s)</b> against outcome <code>${esc(c.recorded_outcome)}</code>, clauses ${esc(c.clauses_cited.join(", ") || "none")}.</p>`;
    const flags = c.flags.map((f) => `<div class="flag ${f.severity}"><span class="code">${esc(f.code)}</span>§${esc(f.clause)} · ${esc(f.severity)}<div>${esc(f.detail)}</div>${f.finding_ids.length ? `<div class="muted" style="font-family:var(--mono);font-size:11px">${f.finding_ids.join(", ")}</div>` : ""}</div>`).join("");
    const faith = c.rationale_faithfulness != null ? `<p>Rationale against the pack: faithfulness <b>${c.rationale_faithfulness.toFixed(2)}</b>${c.unsupported_statements.length ? "<ul>" + c.unsupported_statements.map((s) => `<li>${esc(s)}</li>`).join("") + "</ul>" : " · every statement supported"}</p>` : "";
    $("check-result").innerHTML = head + flags + faith;
  }
  async function loadPack(review) {
    const r = await fetch("/api/workflow/pack/" + encodeURIComponent(review));
    if (!r.ok) return;
    const d = await r.json();
    packState.steps = d.steps || {}; paintSteps();
    if (d.pack) { renderPack(d.pack); if (d.check) renderCheck(d.check); }
    else if (d.status === "error") $("pack-result").innerHTML = `<p class="muted">pack failed: ${esc(d.error)}</p>`;
  }
  $("pack-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const review = $("pack-case").value.trim();
    if (!review) return;
    packState.review = review; packState.steps = {}; packState.tokens = { in: 0, out: 0 }; paintSteps();
    $("pack-result").innerHTML = '<p class="muted">building…</p>'; $("check-panel").hidden = true; $("pack-build").disabled = true;
    const r = await fetch("/api/workflow/pack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review_id: review, use_model: $("pack-model").checked }) });
    if (!r.ok) { $("pack-result").innerHTML = `<p class="muted">${esc((await r.json()).error)}</p>`; $("pack-build").disabled = false; }
  });
  $("check-run").addEventListener("click", async () => {
    $("check-result").innerHTML = '<p class="muted">checking…</p>';
    const body = { review_id: packState.review, recorded_outcome: $("check-outcome").value, clauses: $("check-clauses").value.split(",").map((s) => s.trim()).filter(Boolean), rationale: $("check-rationale").value, use_model: $("pack-model").checked };
    const r = await fetch("/api/workflow/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json();
    if (r.ok) renderCheck(d.check); else $("check-result").innerHTML = `<p class="muted">${esc(d.error)}</p>`;
  });
  function onPackEvent(d) {
    if (packState.review && d.review_id !== packState.review) return;
    const kind = d.event, step = d.step;
    if (step) {
      const st = packState.steps[step] = packState.steps[step] || { status: "pending" };
      if (kind === "step_start") st.status = "running";
      else if (kind === "step_end") { st.status = "done"; st.duration_ms = d.duration_ms; st.exceptions = d.exceptions; }
      else if (kind === "step_skipped") st.status = "skipped";
      else if (kind === "step_error") st.status = "error";
      else if (kind === "model_call") { packState.tokens.in += d.input_tokens || 0; packState.tokens.out += d.output_tokens || 0; $("c-pack").textContent = `${fmt(packState.tokens.in)} / ${fmt(packState.tokens.out)}`; }
      paintSteps();
    }
    const line = kind === "model_call" ? `${step}: ${d.purpose} · stop ${d.stop_reason} · in ${d.input_tokens} out ${d.output_tokens} · ${Math.round(d.latency_ms)} ms`
      : kind === "step_end" ? `${step} done${d.findings != null ? ` · ${d.findings} finding(s), ${d.exceptions || 0} exception(s)` : ""} · ${Math.round(d.duration_ms || 0)} ms`
      : kind === "pack_end" ? `pack done · ${d.findings} findings, ${d.exceptions} exceptions, ${d.model_calls} model calls, in ${d.input_tokens} out ${d.output_tokens}`
      : kind === "pack_status" ? `pack ${d.status}${d.error ? ": " + d.error : ""}` : kind === "check_end" ? `check done · flags ${(d.flags || []).join(", ") || "none"} · clean ${d.clean}` : null;
    if (line) addLog("pack", kind === "step_error" || kind === "model_error" ? "WARNING" : "INFO", `[pack ${d.review_id}] ${line}`, d.ts);
    if (kind === "pack_status") { $("pack-build").disabled = false; loadPack(d.review_id); }
  }

  // ---- costs ------------------------------------------------------------------
  const live = { calls: 0, tools: 0, in: 0, out: 0, cache: 0 };
  function paintCosts() {
    $("c-calls").textContent = fmt(live.calls); $("c-tools").textContent = fmt(live.tools);
    $("c-in").textContent = fmt(live.in); $("c-out").textContent = fmt(live.out); $("c-cache").textContent = fmt(live.cache);
  }
  function resetCosts() { Object.keys(live).forEach((k) => (live[k] = 0)); $("c-turn").textContent = "–"; $("c-turn-tok").textContent = "–"; paintCosts(); }
  function onEvent(e) {
    if (e.event === "model_call") { live.calls += 1; live.in += e.usage.input_tokens; live.out += e.usage.output_tokens; live.cache += e.usage.cache_read_input_tokens || 0; }
    if (e.event === "guardrail_input" && e.model_call && e.model_call.input_tokens !== undefined) { live.calls += 1; live.in += e.model_call.input_tokens; live.out += e.model_call.output_tokens; }
    if (e.event === "guardrail_tool_call") live.tools += 1;
    if (e.event === "user_message") { $("c-turn").textContent = `${e.turn} running`; $("c-turn-tok").textContent = "…"; }
    if (e.event === "turn_end") {
      $("c-turn").textContent = `${e.turn} ${e.outcome}`;
      $("c-turn-tok").textContent = `${fmt(e.input_tokens)} / ${fmt(e.output_tokens)}`;
      const s = e.session_totals; live.calls = s.model_calls; live.tools = s.tool_calls; live.in = s.input_tokens; live.out = s.output_tokens;
    }
    paintCosts();
  }

  // ---- log pane ---------------------------------------------------------------
  const logEl = $("log"); const logLines = [];
  function paintLog() {
    const f = $("log-filter").value.trim().toLowerCase(), warn = $("log-warn").checked;
    logEl.innerHTML = logLines.filter((l) => (!warn || l.level === "WARNING" || l.level === "ERROR") && (!f || l.line.toLowerCase().includes(f)))
      .slice(-400).map((l) => `<div class="l ${l.level} ${l.kind}"><span class="t">${l.ts.slice(11, 19)}</span>${esc(l.line)}</div>`).join("");
    logEl.scrollTop = logEl.scrollHeight;
  }
  function addLog(kind, level, line, ts) { logLines.push({ kind, level, line, ts }); if (logLines.length > 2000) logLines.shift(); paintLog(); }
  $("log-filter").addEventListener("input", paintLog); $("log-warn").addEventListener("change", paintLog);

  // ---- evals -----------------------------------------------------------------------
  document.querySelectorAll("[data-eval]").forEach((b) => b.addEventListener("click", async () => {
    const name = b.dataset.eval;
    const r = await fetch("/api/evals/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    const d = await r.json();
    $("state-" + name).textContent = r.ok ? `${d.status} since ${d.started}` : d.error;
  }));
  async function loadHistory() {
    const h = await (await fetch("/api/evals/history")).json();
    const tbody = $("eval-table").querySelector("tbody"); const rows = [];
    for (const name of Object.keys(h)) for (const r of h[name]) rows.push({ name, ...r });
    rows.sort((a, b) => (a.at < b.at ? 1 : -1));
    tbody.innerHTML = rows.map((r) => `<tr><td>${esc(r.at)}</td><td>${esc(r.name)}</td><td>${esc(r.model)}</td><td>${(r.score ?? 0).toFixed(3)}</td><td>${r.passed}/${r.total}</td><td>${r.judge ? fmt(r.judge.input_tokens) + " / " + fmt(r.judge.output_tokens) : "–"}</td></tr>`).join("");
    drawChart($("chart-routing"), h.routing || [], "mean accuracy"); drawChart($("chart-guardrails"), h.guardrails || [], "pass rate"); drawChart($("chart-pack"), h.pack || [], "overturn recall");
    const last = (h.guardrails || []).slice(-1)[0];
    if (last && last.judge) $("c-judge").textContent = `${fmt(last.judge.input_tokens)} / ${fmt(last.judge.output_tokens)}`;
  }
  // One series per chart (the caption names it), one y-axis 0..1, 2px line, 8px markers, hover tooltip.
  function drawChart(el, runs, label) {
    const W = 460, H = 190, L = 36, R = 12, T = 12, B = 26;
    if (!runs.length) { el.innerHTML = `<svg viewBox="0 0 ${W} ${H}"><text class="empty" x="${L}" y="${H / 2}">no runs yet</text></svg>`; return; }
    const n = runs.length, x = (i) => L + (n === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (n - 1)), y = (v) => T + (1 - v) * (H - T - B);
    let s = `<svg viewBox="0 0 ${W} ${H}">`;
    for (const g of [0, 0.5, 0.9, 1]) s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(g)}" y2="${y(g)}"/><text class="axis" x="${L - 6}" y="${y(g) + 4}" text-anchor="end">${g}</text>`;
    s += `<polyline class="line" points="${runs.map((r, i) => `${x(i)},${y(r.score ?? 0)}`).join(" ")}"/>`;
    runs.forEach((r, i) => { s += `<circle class="dot" cx="${x(i)}" cy="${y(r.score ?? 0)}" r="4"/><rect class="hit" x="${x(i) - 14}" y="${T}" width="28" height="${H - T - B}" data-i="${i}"/>`; });
    s += `<text class="axis" x="${L}" y="${H - 8}">${esc(runs[0].at.slice(0, 16))}</text><text class="axis" x="${W - R}" y="${H - 8}" text-anchor="end">${esc(runs[n - 1].at.slice(0, 16))}</text>`;
    s += `<g id="tip" style="display:none"><rect class="tipbox" width="200" height="34" rx="4"/><text class="tip" x="6" y="14"></text><text class="tip" x="6" y="28"></text></g></svg>`;
    el.innerHTML = s;
    const svg = el.querySelector("svg"), tip = svg.querySelector("#tip"), tx = tip.querySelectorAll("text");
    svg.querySelectorAll(".hit").forEach((h) => {
      h.addEventListener("mouseenter", () => { const r = runs[+h.dataset.i]; const px = Math.min(x(+h.dataset.i) + 8, W - 210);
        tip.setAttribute("transform", `translate(${px},${T})`); tip.style.display = ""; tx[0].textContent = `${r.at.slice(0, 19)} ${r.model}`; tx[1].textContent = `${label} ${(r.score ?? 0).toFixed(3)} · ${r.passed}/${r.total}`; });
      h.addEventListener("mouseleave", () => (tip.style.display = "none"));
    });
  }

  // ---- status + SSE ------------------------------------------------------------------
  async function refreshStatus() {
    const s = await (await fetch("/api/status")).json();
    $("chat-meta").textContent = `model ${s.model} · guard ${s.guard_model ? "regex + " + s.guard_model : "regex"} · ${s.tools.length} tools · session ${s.session_id}`;
    if (s.examples && !examples.length) { examples = s.examples; paintExamples(); }
    $("status-line").textContent = `mcp ${s.mcp}\naudit ${s.audit_log ? s.audit_log.split("/").slice(-1)[0] : ""}`;
    for (const name of Object.keys(s.evals || {})) { const e = s.evals[name]; const el = $("state-" + name); if (el) el.textContent = `${e.status}${e.summary ? " · " + e.summary : ""}`; }
    if (s.demo_reviews && !$("demo-reviews").children.length) $("demo-reviews").innerHTML = s.demo_reviews.map((r) => `<option value="${esc(r)}">`).join("");
    if (s.packs && !packState.review) { const built = Object.keys(s.packs); if (built.length) { packState.review = built[built.length - 1]; $("pack-case").value = packState.review; loadPack(packState.review); } }
    if (s.totals) { live.calls = s.totals.model_calls; live.tools = s.totals.tool_calls; live.in = s.totals.input_tokens; live.out = s.totals.output_tokens; paintCosts(); }
  }
  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.kind === "log") addLog("log", d.level, d.line, d.ts);
    else if (d.kind === "event") onEvent(d);
    else if (d.kind === "eval") {
      if (d.line) addLog("eval", "INFO", `[${d.name}] ${d.line}`, d.ts);
      if (d.status) { $("state-" + d.name).textContent = `${d.status}${d.summary ? " · " + d.summary : ""}`; addLog("eval", d.status === "failed" ? "WARNING" : "INFO", `[${d.name}] ${d.status}`, d.ts); if (d.status !== "running") loadHistory(); }
    } else if (d.kind === "usage" && d.turn === null) resetCosts();
    else if (d.kind === "pack") onPackEvent(d);
  };
  es.onerror = () => addLog("log", "WARNING", "event stream disconnected; retrying", new Date().toISOString());

  refreshStatus(); loadChat(); loadHistory();
})();
