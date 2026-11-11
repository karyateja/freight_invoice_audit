/* Freight Invoice Audit: single-page front end. Vanilla JS, no build step.
 * Every number on screen comes from the Python engine's outputs via /api/*. */
"use strict";

// ------------------------------------------------------------------ html helpers
const raw = (s) => ({ __raw: String(s) });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function val(v) {
  if (v === null || v === undefined || v === false) return "";
  if (Array.isArray(v)) return v.map(val).join("");
  if (typeof v === "object" && "__raw" in v) return v.__raw;
  return esc(v);
}
function html(strings, ...vals) {
  let out = "";
  strings.forEach((s, i) => { out += s + (i < vals.length ? val(vals[i]) : ""); });
  return raw(out);
}
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const main = () => $("#main");
function render(content) { main().innerHTML = content.__raw; }

// ------------------------------------------------------------------ formatting
const nf2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat("en-US");
const money = (v) => (v === null || v === undefined || v === "" ? "—" : nf2.format(Number(v)));
const moneyK = (v) => {
  const n = Number(v);
  if (Math.abs(n) >= 1e6) return "$" + (n / 1e6).toFixed(2) + "M";
  if (Math.abs(n) >= 1e4) return "$" + (n / 1e3).toFixed(1) + "k";
  return "$" + nf2.format(n);
};
const int = (v) => (v === null || v === undefined || v === "" ? "—" : nf0.format(Number(v)));
const pct = (v, d = 1) => (v === null || v === undefined ? "—" : (Number(v) * 100).toFixed(d) + "%");
const ratio = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(4).replace(/0+$/, "").replace(/\.$/, ".0"));
const variance = (v) => {
  const n = Number(v);
  if (v === null || v === undefined || v === "") return html`—`;
  const cls = n > 0 ? "pos" : n < 0 ? "neg" : "";
  return html`<span class="${cls}">${n > 0 ? "+" : ""}${money(n)}</span>`;
};
const dt = (s) => (s ? String(s).replace("T", " ") : "—");
const yn = (v) => (Number(v) ? "Yes" : "No");

const BADGE = {
  APPROVE: ["good", "✓"], DISPUTE: ["warn", "⚑"], REJECT: ["crit", "✕"],
  PASS: ["good", "✓"], FAIL: ["crit", "✕"],
  MATCH: ["good", "✓"], WITHIN_TOLERANCE: ["info", "≈"], EXCEPTION: ["crit", "!"], INVOICE_REJECTED: ["crit", "✕"],
  HIGH: ["crit", "▲"], MEDIUM: ["warn", "●"], LOW: ["", "▼"],
  CREDITED: ["good", "✓"], APPROVED: ["info", "✓"], DISPUTED: ["warn", "⚑"], PENDING_MANAGER_REVIEW: ["warn", "⏳"],
  REJECTED_LATE: ["crit", "✕"], ESCALATED: ["crit", "▲"], CLOSED_WAIVED: ["", "–"], CLOSED_UNDERBILLED_ACCEPTED: ["", "–"],
  CLOSED_INVOICE_REJECTED: ["", "✕"], OPEN: ["info", "○"],
  APPLIED: ["good", "✓"], APPLIED_PARTIAL: ["warn", "◐"], FLAGGED_OVER_CREDIT: ["crit", "!"], RECEIVED: ["info", "○"],
  SETTLED: ["good", "✓"], ON_HOLD: ["warn", "⏸"], REJECTED: ["crit", "✕"], IN_AUDIT: ["info", "○"],
  ANOMALY: ["crit", "!"], CLEAN: ["good", "✓"], BOUNDARY: ["info", "≈"],
  succeeded: ["good", "✓"], failed: ["crit", "✕"], running: ["warn", "⏳"], queued: ["", "○"], cancelled: ["", "–"],
};
function badge(v, title) {
  if (v === null || v === undefined || v === "") return html`<span class="muted">—</span>`;
  const [cls, icon] = BADGE[v] || ["", ""];
  return html`<span class="badge ${cls}" data-icon="${icon ? icon + " " : ""}" title="${title || ""}">${v}</span>`;
}

// ------------------------------------------------------------------ state + api
const state = { ds: null, datasets: [], meta: null, filtersCache: {}, pollers: [] };
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  let data;
  try { data = await res.json(); } catch { data = { error: `HTTP ${res.status}` }; }
  if (!res.ok) { const e = new Error(data.error || `HTTP ${res.status}`); e.status = res.status; throw e; }
  return data;
}
const dsApi = (p, body) => api(`/api/d/${encodeURIComponent(state.ds)}${p}`, body);

function errorBox(e) {
  const hint = e.status === 409 ? " The page will work again once the job finishes (see Run pipeline)." : "";
  return html`<div class="error-box"><strong>Could not load.</strong> ${e.message}${hint}</div>`;
}

async function loadDatasets(preferred) {
  state.datasets = await api("/api/datasets");
  const sel = $("#dataset");
  const usable = state.datasets.filter((d) => !d.busy);
  const want = preferred || state.ds || store.get("ds");
  state.ds = (usable.find((d) => d.name === want) || usable.find((d) => d.name === "starter") || usable[0] || {}).name || null;
  sel.innerHTML = state.datasets.map((d) => {
    const label = `${d.name}${d.busy ? " (regenerating…)" : ""}${d.has_db === false ? " (reports only)" : ""}`;
    return `<option value="${esc(d.name)}" ${d.busy ? "disabled" : ""} ${d.name === state.ds ? "selected" : ""}>${esc(label)}</option>`;
  }).join("") || `<option value="">no datasets yet</option>`;
  if (state.ds) store.set("ds", state.ds);
}

async function filterOptions() {
  if (!state.filtersCache[state.ds]) state.filtersCache[state.ds] = await dsApi("/filters");
  return state.filtersCache[state.ds];
}

// ------------------------------------------------------------------ router
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "") || "overview";
  const [path, qs] = h.split("?");
  return { parts: path.split("/").map(decodeURIComponent), params: new URLSearchParams(qs || "") };
}
function go(path, params) {
  const qs = params && [...params].length ? "?" + params.toString() : "";
  location.hash = "#/" + path + qs;
}
const ROUTES = {
  overview: viewOverview, exceptions: viewExceptions, invoices: viewInvoices, shipments: viewShipment,
  carriers: viewCarriers, calculator: viewCalculator, validation: viewValidation, sql: viewSql, rules: viewRules, run: viewRun,
};
const NEEDS_DS = new Set(["overview", "exceptions", "invoices", "shipments", "carriers", "calculator", "validation", "sql"]);

async function route() {
  state.pollers.forEach(clearInterval);
  state.pollers = [];
  hideTip();
  const { parts, params } = parseHash();
  const view = ROUTES[parts[0]] ? parts[0] : "overview";
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === (view === "shipments" ? "invoices" : view)));
  if (NEEDS_DS.has(view) && !state.ds) {
    render(html`<div class="notice">No dataset yet. Generate one on the <a href="#/run">Run pipeline</a> page.</div>`);
    return;
  }
  render(html`<div class="loading">Loading…</div>`);
  try {
    await ROUTES[view](parts.slice(1), params);
  } catch (e) {
    console.error(e);
    render(errorBox(e));
  }
}

// ------------------------------------------------------------------ tooltip
const tip = () => $("#tooltip");
function showTip(text, ev) {
  const t = tip();
  t.textContent = text;
  t.hidden = false;
  const x = Math.min(ev.clientX + 14, window.innerWidth - t.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - t.offsetHeight - 8);
  t.style.left = x + "px";
  t.style.top = y + "px";
}
function hideTip() { if (tip()) tip().hidden = true; }
document.addEventListener("mousemove", (ev) => {
  const el = ev.target.closest && ev.target.closest("[data-tip]");
  if (el) showTip(el.dataset.tip, ev); else hideTip();
});

// ------------------------------------------------------------------ charts
function hbars(items, { href, fmt = int } = {}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return html`<div class="hbars" role="list">${items.map((i) => html`
    <a class="row-hit" role="listitem" ${href ? raw(`href="${esc(href(i))}"`) : ""} data-tip="${i.label}: ${fmt(i.value)}${i.extra ? " · " + i.extra : ""}">
      <span class="lbl">${i.label}</span>
      <span class="track"><span class="bar" style="width:${((i.value / max) * 100).toFixed(2)}%;display:block"></span></span>
      <span class="val">${fmt(i.value)}</span>
    </a>`)}</div>`;
}
function segBar(items) {
  const total = items.reduce((s, i) => s + i.value, 0) || 1;
  return html`
    <div class="seg" role="img" aria-label="${items.map((i) => `${i.label} ${i.value}`).join(", ")}">
      ${items.filter((i) => i.value > 0).map((i) => html`<div style="flex:${i.value};background:${i.color}" data-tip="${i.label}: ${int(i.value)} (${pct(i.value / total)})"></div>`)}
    </div>
    <div class="legend">${items.map((i) => html`<span><i style="background:${i.color}"></i>${i.icon} ${i.label} <strong>${int(i.value)}</strong> <span class="muted">${pct(i.value / total)}</span></span>`)}</div>`;
}

// ------------------------------------------------------------------ generic list view
function sortHeader(col, params) {
  if (!col.sort) return html`<th class="${col.num ? "num" : ""}">${col.label}</th>`;
  const active = params.get("sort") === col.sort;
  const dir = active && params.get("dir") === "desc" ? "desc" : "asc";
  return html`<th class="sortable ${col.num ? "num" : ""}" data-sort="${col.sort}" aria-sort="${active ? (dir === "asc" ? "ascending" : "descending") : "none"}">
    ${col.label} <span class="arrow">${active ? (dir === "asc" ? "↑" : "↓") : ""}</span></th>`;
}

async function listView({ route: r, title, sub, endpoint, columns, filters, params, rowHref, extraTop }) {
  const q = new URLSearchParams(params);
  if (!q.get("size")) q.set("size", "50");
  const data = await dsApi(`${endpoint}?${q}`);
  const pages = Math.max(1, Math.ceil(data.total / data.size));
  render(html`
    <div class="page-head"><div><h1>${title}</h1><div class="sub">${sub}</div></div></div>
    ${extraTop || ""}
    <form class="filters" id="filters">
      ${filters.map((f) => f.options ? html`
        <select name="${f.name}" aria-label="${f.label}">
          <option value="">${f.label}: all</option>
          ${f.options.map((o) => { const [v, l] = Array.isArray(o) ? o : [o, o]; return html`<option value="${v}" ${params.get(f.name) === v ? raw("selected") : ""}>${l}</option>`; })}
        </select>` : html`<input type="search" name="${f.name}" placeholder="${f.label}" value="${params.get(f.name) || ""}" aria-label="${f.label}">`)}
      <button class="btn small" type="submit">Apply</button>
      <button class="btn ghost small" type="button" id="clear">Clear</button>
      <span class="muted" style="margin-left:auto">${int(data.total)} rows</span>
    </form>
    <div class="card" style="padding:6px 8px">
      <div class="table-wrap"><table>
        <thead><tr>${columns.map((c) => sortHeader(c, params))}</tr></thead>
        <tbody>${data.rows.length ? data.rows.map((row) => html`
          <tr class="click" data-href="${rowHref(row)}">${columns.map((c) => html`<td class="${c.num ? "num" : ""} ${c.wrap ? "wrap" : ""}">${c.fmt ? c.fmt(row[c.key], row) : row[c.key] ?? ""}</td>`)}</tr>`)
          : html`<tr><td colspan="${columns.length}" class="empty">No rows match these filters.</td></tr>`}
        </tbody></table></div>
    </div>
    <div class="pager">
      <button class="btn ghost small" id="prev" ${data.page <= 1 ? raw("disabled") : ""}>← Prev</button>
      <span>Page ${data.page} of ${pages}</span>
      <button class="btn ghost small" id="next" ${data.page >= pages ? raw("disabled") : ""}>Next →</button>
    </div>`);
  const nav = (mut) => { const p = new URLSearchParams(params); mut(p); go(r, p); };
  $("#filters").addEventListener("submit", (ev) => {
    ev.preventDefault();
    nav((p) => { new FormData(ev.target).forEach((v, k) => (v ? p.set(k, v) : p.delete(k))); p.delete("page"); });
  });
  $$("#filters select").forEach((s) => s.addEventListener("change", () => $("#filters").requestSubmit()));
  $("#clear").addEventListener("click", () => go(r, new URLSearchParams()));
  $("#prev").addEventListener("click", () => nav((p) => p.set("page", data.page - 1)));
  $("#next").addEventListener("click", () => nav((p) => p.set("page", data.page + 1)));
  $$("th.sortable").forEach((th) => th.addEventListener("click", () => nav((p) => {
    const same = p.get("sort") === th.dataset.sort;
    p.set("sort", th.dataset.sort);
    p.set("dir", same && p.get("dir") !== "desc" ? "desc" : "asc");
    p.delete("page");
  })));
  bindRowLinks();
}
function bindRowLinks() {
  $$("tr[data-href]").forEach((tr) => tr.addEventListener("click", (ev) => {
    if (ev.target.closest("a")) return;
    location.hash = tr.dataset.href;
  }));
}

// ------------------------------------------------------------------ overview
async function viewOverview() {
  const o = await dsApi("/overview");
  const k = o.kpis || {};
  const m = o.manifest;
  const e = o.expected_charge_reproduction || {};
  const x = o.explanation_completeness || {};
  const cr = o.credit_reconciliation || {};
  const dup = (o.detection.per_issue_type || {}).DUPLICATE_INVOICE || {};
  const crit = [
    { ok: e.line_match_rate === 1, name: "Expected charges are reproducible", detail: `${int(e.lines_exact_match)} / ${int(e.lines)} lines re-rated to exactly the ground-truth amount`, value: pct(e.line_match_rate, 2) },
    { ok: x.lines_with_unexplained_variance === 0, name: "Exceptions explain line-level differences", detail: "lines whose variance is not covered by an exception or the rounding tolerance", value: `${int(x.lines_with_unexplained_variance)} unexplained` },
    { ok: dup.recall === 1 && dup.precision === 1, name: "Duplicate bills are detected", detail: "DUPLICATE_INVOICE recall / precision vs labels", value: `${ratio(dup.recall)} / ${ratio(dup.precision)}` },
    { ok: cr.credits_without_approved_dispute === 0 && (cr.over_credit_detection || {}).recall === 1, name: "Credits reconcile to approved disputes", detail: `${int(cr.credits_without_approved_dispute)} credits without an approved dispute; over-credit recall ${ratio((cr.over_credit_detection || {}).recall)}`, value: `${int(cr.credited_disputes_reconciled_exactly)} exact` },
  ];
  const dec = k.decisions || {};
  const byType = Object.entries(k.exceptions_by_type || {}).map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
  const byStatus = Object.entries(k.exceptions_by_status || {}).map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
  const det = o.detection;
  const v = o.validation;
  render(html`
    <div class="page-head">
      <div>
        <h1>Audit overview <span class="muted" style="font-weight:400">· ${o.name}</span></h1>
        <div class="sub">Scale <strong>${m.scale.name}</strong> · seed <code>${m.seed}</code> · ${int(m.scale.carriers)} carriers, ${int(m.scale.shipments)} shipments, ${int(m.scale.invoices)} invoices · as of ${dt(m.as_of)} · generated ${dt(m.generated_at_utc)} UTC in ${m.runtime_seconds}s</div>
      </div>
      <a class="btn ghost" href="#/validation">${badge(v.overall)}&nbsp; ${v.checks_total - v.checks_failed}/${v.checks_total} validation checks</a>
    </div>
    ${!o.has_db ? html`<div class="notice">Only reports were kept for this dataset (the data files are git-ignored at this scale). Drill-downs need the database: regenerate it on the <a href="#/run">Run pipeline</a> page.</div>` : ""}
    <div class="tiles">
      <div class="tile"><div class="label">Invoices audited</div><div class="value">${int(k.invoices_audited)}</div><div class="note">${pct(k.invoice_exception_rate)} with an exception</div></div>
      <div class="tile"><div class="label">Billed by carriers</div><div class="value">${moneyK(k.billed_amount)}</div><div class="note">contract value ${moneyK(k.expected_amount)}</div></div>
      <div class="tile"><div class="label">Overbilling identified</div><div class="value">${moneyK(k.overbilling_identified_amount)}</div><div class="note">disputed ${moneyK(k.disputed_amount)}</div></div>
      <div class="tile"><div class="label">Rejected invoices prevented</div><div class="value">${moneyK(k.rejected_invoice_amount_prevented)}</div><div class="note">duplicates, unknown shipments…</div></div>
      <div class="tile"><div class="label">Net savings</div><div class="value">${moneyK(k.net_savings_amount)}</div><div class="note">${pct(k.savings_rate_of_billed, 2)} of billed · ${moneyK(k.lost_to_late_dispute_amount)} lost to late disputes</div></div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Acceptance criteria</h2><a href="/files/${o.name}/reports/evaluation_report.md" target="_blank">evaluation_report.md</a></div>
        <ul class="crit-list">${crit.map((c) => html`
          <li><span class="${c.ok ? "ok-icon" : "bad-icon"}" aria-label="${c.ok ? "met" : "not met"}">${c.ok ? "✓" : "✕"}</span>
              <span><strong>${c.name}</strong><br><span class="muted">${c.detail}</span></span>
              <span class="nowrap">${c.value}</span></li>`)}</ul>
      </div>
      <div class="card">
        <div class="card-head"><h2>Invoice decisions</h2><a href="#/invoices">all invoices →</a></div>
        ${segBar([
          { label: "APPROVE", icon: "✓", value: dec.APPROVE || 0, color: "var(--good)" },
          { label: "DISPUTE", icon: "⚑", value: dec.DISPUTE || 0, color: "var(--warning)" },
          { label: "REJECT", icon: "✕", value: dec.REJECT || 0, color: "var(--critical)" },
        ])}
        <h3>Decision vs ground truth</h3>
        <p>Accuracy <strong>${pct((o.decision_accuracy || {}).accuracy, 2)}</strong> · ${Object.entries((o.decision_accuracy || {}).confusion_expected_vs_predicted || {}).map(([a, n]) => `${a}: ${n}`).join(" · ")}</p>
        <p class="muted">Detection (micro): precision <strong>${ratio(det.micro?.precision)}</strong>, recall <strong>${ratio(det.micro?.recall)}</strong>, F1 ${ratio(det.micro?.f1)} · false-positive rate on non-anomalous invoices ${ratio(det.false_positive_rate_non_anomalous)}</p>
      </div>
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Exceptions by root cause</h2><span class="muted">click a bar to filter</span></div>
        ${hbars(byType, { href: (i) => `#/exceptions?type=${encodeURIComponent(i.label)}` })}
      </div>
      <div class="card">
        <div class="card-head"><h2>Exceptions by lifecycle status</h2></div>
        ${hbars(byStatus, { href: (i) => `#/exceptions?status=${encodeURIComponent(i.label)}` })}
      </div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Detection vs labelled ground truth (invoice level)</h2><span class="muted">TP / FP / FN per issue type</span></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Issue type</th><th class="num">TP</th><th class="num">FP</th><th class="num">FN</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th></tr></thead>
        <tbody>${Object.entries(det.per_issue_type || {}).map(([t, r]) => html`
          <tr><td><a href="#/exceptions?type=${t}">${t}</a></td><td class="num">${r.tp}</td><td class="num">${r.fp}</td><td class="num">${r.fn}</td>
          <td class="num">${ratio(r.precision)}</td><td class="num">${ratio(r.recall)}</td><td class="num">${ratio(r.f1)}</td></tr>`)}</tbody>
      </table></div>
    </div>
    <div class="card">
      <div class="card-head"><h2>Carrier scorecard</h2><a href="#/carriers">carriers →</a></div>
      ${scorecardTable(o.scorecard.slice().sort((a, b) => b.overbilled_amount - a.overbilled_amount).slice(0, 10))}
      ${o.scorecard.length > 10 ? html`<p class="muted" style="margin-top:8px">Top 10 by overbilled amount, ${o.scorecard.length} carriers in total.</p>` : ""}
    </div>
    <div class="grid g2">
      <div class="card">
        <div class="card-head"><h2>Credit reconciliation</h2></div>
        <dl class="kv">${Object.entries(cr).filter(([, x]) => typeof x !== "object").map(([key, x]) => html`<dt>${key.replace(/_/g, " ")}</dt><dd>${/amount/.test(key) ? money(x) : int(x)}</dd>`)}</dl>
      </div>
      <div class="card">
        <div class="card-head"><h2>Output files</h2><span class="muted">${o.files.length} files · SHA-256 in manifest</span></div>
        <div class="files">${o.files.filter((f) => !f.path.startsWith("data/json") && !f.path.endsWith(".sqlite")).map((f) => html`<a href="/files/${o.name}/${f.path}" target="_blank" title="${f.sha256}">${f.path}${f.rows !== null ? html` <span class="muted">(${int(f.rows)})</span>` : ""}</a>`)}</div>
      </div>
    </div>`);
}

function scorecardTable(rows) {
  return html`<div class="table-wrap"><table>
    <thead><tr><th>Carrier</th><th class="num">Invoices</th><th class="num">Clean rate</th><th class="num">Rejected</th><th class="num">Disputed</th><th class="num">Billed</th><th class="num">Overbilled</th><th class="num">Credited</th><th class="num">Over-credits</th></tr></thead>
    <tbody>${rows.map((r) => html`<tr class="click" data-href="#/carriers/${r.carrier_id}">
      <td><a href="#/carriers/${r.carrier_id}">${r.carrier_id}</a> <span class="muted">${r.carrier_name}</span></td>
      <td class="num">${int(r.invoices)}</td><td class="num">${pct(r.clean_invoice_rate)}</td><td class="num">${int(r.rejected_invoices)}</td>
      <td class="num">${int(r.disputed_invoices)}</td><td class="num">${money(r.billed_amount)}</td><td class="num">${money(r.overbilled_amount)}</td>
      <td class="num">${money(r.credited_amount)}</td><td class="num">${int(r.over_credit_notes)}</td></tr>`)}</tbody></table></div>`;
}

// ------------------------------------------------------------------ exceptions
async function viewExceptions(rest, params) {
  if (rest[0]) return viewExceptionDetail(rest[0]);
  const f = await filterOptions();
  await listView({
    route: "exceptions", title: "Audit exceptions", params,
    sub: "One record per discrepant line or failed invoice-level rule, with root cause, rule id and explanation.",
    endpoint: "/exceptions",
    filters: [
      { name: "type", label: "Type", options: f.exception_types },
      { name: "status", label: "Status", options: f.exception_statuses },
      { name: "severity", label: "Severity", options: ["HIGH", "MEDIUM", "LOW"] },
      { name: "carrier", label: "Carrier", options: f.carriers.map((c) => [c.carrier_id, `${c.carrier_id} ${c.carrier_name}`]) },
      { name: "q", label: "Search id or explanation…" },
    ],
    columns: [
      { key: "exception_id", label: "Exception", sort: "exception_id", fmt: (v) => html`<a href="#/exceptions/${v}" class="mono">${v}</a>` },
      { key: "exception_type", label: "Type", sort: "type", fmt: (v, r) => html`${v}<br><span class="muted">${r.rule_id}</span>` },
      { key: "invoice_id", label: "Invoice", fmt: (v) => (v ? html`<a href="#/invoices/${v}" class="mono">${v}</a>` : "—") },
      { key: "carrier_id", label: "Carrier", sort: "carrier" },
      { key: "severity", label: "Severity", sort: "severity", fmt: (v) => badge(v) },
      { key: "variance_amount", label: "Variance", num: true, sort: "variance", fmt: variance },
      { key: "status", label: "Status", sort: "status", fmt: (v) => badge(v) },
      { key: "explanation", label: "Explanation", wrap: true, fmt: (v) => html`<span class="muted">${v}</span>` },
    ],
    rowHref: (r) => `#/exceptions/${r.exception_id}`,
  });
}

async function viewExceptionDetail(id) {
  const d = await dsApi(`/exceptions/${encodeURIComponent(id)}`);
  const e = d.exception;
  render(html`
    <div class="page-head"><div>
      <div class="muted"><a href="#/exceptions">Exceptions</a> /</div>
      <h1 class="mono">${e.exception_id}</h1>
      <div class="sub">${e.exception_type} · rule <code>${e.rule_id}</code> · ${badge(e.severity)} ${badge(e.status)}</div>
    </div></div>
    <div class="grid g2">
      <div class="card">
        <h2>What the audit found</h2>
        <div class="explain">${e.explanation}</div>
        <dl class="kv">
          <dt>Invoice</dt><dd>${e.invoice_id ? html`<a class="mono" href="#/invoices/${e.invoice_id}">${e.invoice_id}</a>` : "—"}</dd>
          <dt>Invoice line</dt><dd class="mono">${e.invoice_line_id || "— (invoice-level rule)"}</dd>
          ${e.credit_note_id ? html`<dt>Credit note</dt><dd class="mono">${e.credit_note_id}</dd>` : ""}
          <dt>Carrier</dt><dd>${e.carrier_id ? html`<a href="#/carriers/${e.carrier_id}">${e.carrier_id}</a> ${e.carrier_name}` : "—"}</dd>
          <dt>Shipment</dt><dd>${e.shipment_id ? html`<a class="mono" href="#/shipments/${e.shipment_id}">${e.shipment_id}</a>` : "—"}</dd>
          <dt>Billed</dt><dd>${money(e.billed_amount)}</dd>
          <dt>Expected (contract)</dt><dd>${money(e.expected_amount)}</dd>
          <dt>Variance</dt><dd>${variance(e.variance_amount)}</dd>
          <dt>Approved amount</dt><dd>${money(e.approved_amount)}</dd>
          <dt>Assigned to</dt><dd>${e.assigned_role}</dd>
          <dt>Detected</dt><dd>${dt(e.detected_at)}</dd>
        </dl>
      </div>
      <div class="card">
        <h2>Lifecycle (append-only events)</h2>
        ${timeline(d.events)}
      </div>
    </div>
    ${d.line ? html`<div class="card"><h2>Disputed line</h2>${linesTable([d.line])}</div>` : ""}
    ${d.credit_notes.length ? html`<div class="card"><h2>Carrier credit notes</h2>${creditTable(d.credit_notes)}</div>` : ""}
    <div class="card gt"><h2>Ground truth</h2>${d.ground_truth.length ? gtTable(d.ground_truth) : html`<p class="muted">No label for this invoice: it was generated as a clean or boundary case.</p>`}</div>`);
}

function timeline(events) {
  if (!events.length) return html`<p class="muted">No events.</p>`;
  return html`<ol class="timeline">${events.map((ev) => html`
    <li><div><strong>${ev.from_status ? `${ev.from_status} → ` : ""}${ev.to_status}</strong> <span class="muted">by ${ev.actor_role}</span></div>
    <div class="t">${dt(ev.event_at)}${ev.note ? " · " : ""}${ev.note || ""}</div></li>`)}</ol>`;
}
function creditTable(rows) {
  return html`<div class="table-wrap"><table><thead><tr><th>Credit note</th><th>Carrier ref</th><th>Exception</th><th>Issued</th><th class="num">Credit</th><th class="num">Reconciled</th><th class="num">Excess</th><th>Status</th></tr></thead>
    <tbody>${rows.map((c) => html`<tr class="${c.status === "FLAGGED_OVER_CREDIT" ? "bad" : ""}"><td class="mono">${c.credit_note_id}</td><td class="mono">${c.carrier_credit_ref}</td>
      <td><a class="mono" href="#/exceptions/${c.exception_id}">${c.exception_id}</a></td><td>${dt(c.issued_at)}</td><td class="num">${money(c.credit_amount)}</td>
      <td class="num">${money(c.reconciled_amount)}</td><td class="num">${money(c.excess_amount)}</td><td>${badge(c.status)}</td></tr>`)}</tbody></table></div>`;
}
function gtTable(rows) {
  return html`<div class="table-wrap"><table><thead><tr><th>Label</th><th>Entity</th><th>Issue type</th><th>Class</th><th>Expected decision</th><th class="num">Expected variance</th><th>How it was injected</th></tr></thead>
    <tbody>${rows.map((g) => html`<tr><td class="mono">${g.gt_id}</td><td class="mono">${g.entity_id}</td><td>${g.issue_type}</td><td>${badge(g.case_class)}</td>
      <td>${badge(g.expected_decision)}</td><td class="num">${variance(g.expected_variance)}</td><td class="wrap muted">${g.injection_detail}</td></tr>`)}</tbody></table></div>`;
}

// ------------------------------------------------------------------ invoices
async function viewInvoices(rest, params) {
  if (rest[0]) return viewInvoiceDetail(rest[0]);
  const f = await filterOptions();
  await listView({
    route: "invoices", title: "Freight invoices", params,
    sub: "Every carrier bill with the audit verdict: re-rated from source records, never from the carrier's numbers.",
    endpoint: "/invoices",
    filters: [
      { name: "decision", label: "Decision", options: ["APPROVE", "DISPUTE", "REJECT"] },
      { name: "status", label: "Status", options: f.invoice_statuses },
      { name: "type", label: "Type", options: ["ORIGINAL", "SUPPLEMENTAL"] },
      { name: "carrier", label: "Carrier", options: f.carriers.map((c) => [c.carrier_id, `${c.carrier_id} ${c.carrier_name}`]) },
      { name: "q", label: "Invoice, shipment or carrier no.…" },
    ],
    columns: [
      { key: "invoice_id", label: "Invoice", sort: "invoice_id", fmt: (v) => html`<a class="mono" href="#/invoices/${v}">${v}</a>` },
      { key: "carrier_id", label: "Carrier", sort: "carrier", fmt: (v, r) => html`${v}<br><span class="muted">${r.carrier_name}</span>` },
      { key: "shipment_id", label: "Shipment", fmt: (v) => html`<span class="mono">${v}</span>` },
      { key: "invoice_type", label: "Type" },
      { key: "received_date", label: "Received", sort: "received" },
      { key: "billed_total", label: "Billed", num: true, sort: "billed", fmt: money },
      { key: "expected_total", label: "Expected", num: true, fmt: money },
      { key: "variance_total", label: "Variance", num: true, sort: "variance", fmt: variance },
      { key: "exception_count", label: "Exc.", num: true, sort: "exceptions" },
      { key: "decision", label: "Decision", sort: "decision", fmt: (v, r) => badge(v, r.decision_reason) },
      { key: "status", label: "Status", fmt: (v) => badge(v) },
    ],
    rowHref: (r) => `#/invoices/${r.invoice_id}`,
  });
}

function linesTable(lines) {
  const tot = lines.reduce((a, l) => ({ b: a.b + Number(l.amount), e: a.e + Number(l.expected_amount) }), { b: 0, e: 0 });
  return html`<div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Line</th><th>Rate card</th><th>Tier / weight</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Billed</th><th class="num">Expected</th><th class="num">Variance</th><th>Result</th></tr></thead>
    <tbody>${lines.map((l) => html`<tr class="${l.line_result === "EXCEPTION" ? "bad" : ""}">
      <td>${l.line_no}</td>
      <td>${l.line_type}${l.accessorial_code ? html`<br><span class="muted">${l.accessorial_code} ${l.accessorial_name || ""}</span>` : ""}</td>
      <td class="mono">${l.rate_card_id || "—"}</td>
      <td>${l.weight_tier || ""}${l.billed_weight_lb !== null && l.billed_weight_lb !== undefined ? html`<br><span class="muted">${l.billed_weight_lb} lb</span>` : ""}</td>
      <td class="num">${l.quantity}</td><td>${l.unit}</td><td class="num">${l.rate}</td>
      <td class="num">${money(l.amount)}</td><td class="num">${money(l.expected_amount)}</td><td class="num">${variance(l.variance_amount)}</td>
      <td>${badge(l.line_result)}${l.exception_id ? html`<br><a class="mono" href="#/exceptions/${l.exception_id}">${l.exception_id}</a>` : ""}</td></tr>`)}
      ${lines.length > 1 ? html`<tr class="total-row"><td colspan="7">Total</td><td class="num">${money(tot.b)}</td><td class="num">${money(tot.e)}</td><td class="num">${variance(tot.b - tot.e)}</td><td></td></tr>` : ""}
    </tbody></table></div>`;
}

async function viewInvoiceDetail(id) {
  const d = await dsApi(`/invoices/${encodeURIComponent(id)}`);
  const i = d.invoice;
  const a = d.audit;
  const gt = d.ground_truth;
  const agree = gt && gt.expected_decision === a.decision;
  render(html`
    <div class="page-head"><div>
      <div class="muted"><a href="#/invoices">Invoices</a> /</div>
      <h1 class="mono">${i.invoice_id}</h1>
      <div class="sub">Carrier no. <code>${i.carrier_invoice_number}</code> · ${i.invoice_type}${i.original_invoice_id ? html` of <a class="mono" href="#/invoices/${i.original_invoice_id}">${i.original_invoice_id}</a>` : ""} · status ${badge(i.status)}</div>
    </div>
    <div style="text-align:right"><div style="font-size:12px" class="muted">Audit decision</div>${badge(a.decision)}<div class="muted" style="font-size:12.5px;margin-top:4px">${a.decision_reason}</div></div></div>
    <div class="tiles">
      <div class="tile"><div class="label">Billed total</div><div class="value">${money(i.billed_total)}</div></div>
      <div class="tile"><div class="label">Expected (re-rated)</div><div class="value">${money(a.expected_total)}</div></div>
      <div class="tile"><div class="label">Variance</div><div class="value">${variance(a.variance_total)}</div><div class="note">exceptions ${money(a.exception_variance_total)} · tolerated ${money(a.tolerated_variance_total)}</div></div>
      <div class="tile"><div class="label">Exceptions</div><div class="value">${int(a.exception_count)}</div><div class="note">audited ${dt(a.audited_at)}</div></div>
    </div>
    <div class="card"><div class="card-head"><h2>Lines: billed vs contract</h2><span class="muted">expected = re-rated from the rate card, authoritative weight and delivery evidence</span></div>${linesTable(d.lines)}</div>
    ${d.exceptions.length ? html`<div class="card"><h2>Exceptions raised</h2>${d.exceptions.map((e) => html`
      <div style="margin-bottom:10px"><a class="mono" href="#/exceptions/${e.exception_id}">${e.exception_id}</a> · <strong>${e.exception_type}</strong> <span class="muted">${e.rule_id}</span> ${badge(e.severity)} ${badge(e.status)}
      <div class="explain">${e.explanation}</div></div>`)}</div>` : ""}
    <div class="grid g2">
      <div class="card">
        <h2>Context</h2>
        <dl class="kv">
          <dt>Carrier</dt><dd><a href="#/carriers/${i.carrier_id}">${i.carrier_id}</a> ${i.carrier_name}</dd>
          <dt>Shipment</dt><dd>${d.shipment_exists ? html`<a class="mono" href="#/shipments/${i.shipment_id}">${i.shipment_id}</a> · <a href="#/calculator?shipment=${i.shipment_id}">rate it in the calculator</a>` : html`<span class="mono">${i.shipment_id}</span> <span class="badge crit">not in shipment master</span>`}</dd>
          <dt>Invoice date</dt><dd>${i.invoice_date}</dd><dt>Received</dt><dd>${i.received_date}</dd><dt>Due</dt><dd>${i.due_date}</dd>
        </dl>
        ${d.related_invoices.length ? html`<h3>Other invoices for this shipment</h3>
          <table><tbody>${d.related_invoices.map((r) => html`<tr><td><a class="mono" href="#/invoices/${r.invoice_id}">${r.invoice_id}</a></td><td>${r.invoice_type}</td><td>${r.received_date}</td><td class="num">${money(r.billed_total)}</td><td>${badge(r.decision)}</td></tr>`)}</tbody></table>` : ""}
      </div>
      <div class="card"><h2>Invoice history</h2>${timeline(d.events)}</div>
    </div>
    ${d.credit_notes.length ? html`<div class="card"><h2>Credit notes</h2>${creditTable(d.credit_notes)}</div>` : ""}
    <div class="card gt">
      <h2>Ground truth</h2>
      ${gt ? html`<p>Scenario ${badge(gt.scenario_class)} ${gt.issue_type ? html`<strong>${gt.issue_type}</strong>` : ""} · expected decision ${badge(gt.expected_decision)} · expected total ${money(gt.expected_total)}
        · <strong class="${agree ? "ok-icon" : "bad-icon"}">${agree ? "✓ audit agrees" : "✕ audit disagrees"}</strong>
        ${Number(gt.uses_carrier_reweigh) ? html` · <span class="badge info">carrier reweigh</span>` : ""}${Number(gt.dim_weight_governs) ? html` · <span class="badge info">dim weight governs</span>` : ""}</p>
        ${d.ground_truth_labels.length ? gtTable(d.ground_truth_labels) : ""}` : html`<p class="muted">No ground truth row.</p>`}
    </div>`);
}

// ------------------------------------------------------------------ shipments
async function viewShipment(rest) {
  const d = await dsApi(`/shipments/${encodeURIComponent(rest[0] || "")}`);
  const s = d.shipment;
  const dl = d.delivery;
  const flags = ["liftgate_used", "residential_delivery", "inside_delivery", "appointment_required", "limited_access"];
  render(html`
    <div class="page-head"><div>
      <div class="muted"><a href="#/invoices">Invoices</a> / shipment</div>
      <h1 class="mono">${s.shipment_id}</h1>
      <div class="sub">${s.origin_city}, ${s.origin_state} → ${s.dest_city}, ${s.dest_state} · ${int(s.distance_miles)} mi (${s.distance_band}) · ${s.service_level} · ${badge(s.status)}</div>
    </div><a class="btn" href="#/calculator?shipment=${s.shipment_id}">Rate this shipment →</a></div>
    <div class="grid g2">
      <div class="card"><h2>Shipment</h2><dl class="kv">
        <dt>Supplier</dt><dd>${s.supplier_id} ${s.supplier_name}</dd>
        <dt>Carrier</dt><dd><a href="#/carriers/${s.carrier_id}">${s.carrier_id}</a> ${s.carrier_name}</dd>
        <dt>Lane</dt><dd class="mono">${s.lane_id}</dd><dt>Pieces</dt><dd>${s.pieces}</dd><dt>Hazmat</dt><dd>${yn(s.hazmat)}</dd>
        <dt>Booked</dt><dd>${dt(s.booked_at)}</dd><dt>Ship date</dt><dd>${s.ship_date}</dd>
        <dt>Promised</dt><dd>${s.promised_delivery_date}</dd><dt>Delivered</dt><dd>${dt(s.delivered_at)}</dd></dl></div>
      <div class="card"><h2>Delivery record (accessorial evidence)</h2>${dl ? html`<dl class="kv">
        <dt>Delivery</dt><dd class="mono">${dl.delivery_id}</dd><dt>POD</dt><dd class="mono">${dl.pod_reference}</dd>
        <dt>Performance</dt><dd>${badge(dl.delivery_performance)}</dd>
        ${flags.map((f) => html`<dt>${f.replace(/_/g, " ")}</dt><dd>${Number(dl[f]) ? html`<strong>Yes</strong>` : "No"}</dd>`)}
        <dt>Wait minutes</dt><dd>${dl.wait_minutes} <span class="muted">(detention after 120)</span></dd></dl>` : html`<p class="muted">Not delivered yet: no accessorial except hazmat can be evidenced.</p>`}</div>
    </div>
    <div class="card"><h2>Weight measurements</h2><p class="muted">Rule W1: the latest carrier reweigh is authoritative, otherwise the latest shipper declaration.</p>
      <div class="table-wrap"><table><thead><tr><th>Measurement</th><th>Source</th><th>By</th><th>At</th><th class="num">Pieces</th><th>L×W×H in</th><th class="num">Actual lb</th><th class="num">Divisor</th><th class="num">Dim lb</th><th class="num">Billable lb</th><th></th></tr></thead>
      <tbody>${d.measurements.map((m) => html`<tr class="${m.authoritative ? "hl" : ""}"><td class="mono">${m.measurement_id}</td><td>${m.source}</td><td>${m.recorded_by_role}</td><td>${dt(m.measured_at)}</td>
        <td class="num">${m.pieces}</td><td>${m.length_in}×${m.width_in}×${m.height_in}</td><td class="num">${m.actual_weight_lb}</td><td class="num">${m.dim_divisor}</td>
        <td class="num">${m.dim_weight_lb}</td><td class="num"><strong>${m.billable_weight_lb}</strong></td><td>${m.authoritative ? html`<span class="badge info">authoritative</span>` : ""}</td></tr>`)}</tbody></table></div></div>
    <div class="grid g2">
      <div class="card"><h2>Legs</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>Type</th><th>From → to</th><th class="num">Miles</th><th>Departed</th><th>Arrived</th><th>Status</th></tr></thead>
        <tbody>${d.legs.map((l) => html`<tr><td>${l.leg_seq}</td><td>${l.leg_type}</td><td>${l.origin_city} → ${l.dest_city}</td><td class="num">${int(l.leg_miles)}</td><td class="nowrap">${dt(l.actual_departure_at)}</td><td class="nowrap">${dt(l.actual_arrival_at)}</td><td>${l.leg_status}</td></tr>`)}</tbody></table></div></div>
      <div class="card"><h2>Shipment history</h2>${timeline(d.events)}</div>
    </div>
    <div class="card"><h2>Invoices for this shipment</h2>${d.invoices.length ? html`<table><thead><tr><th>Invoice</th><th>Type</th><th>Received</th><th class="num">Billed</th><th class="num">Expected</th><th>Decision</th><th>Status</th></tr></thead>
      <tbody>${d.invoices.map((r) => html`<tr class="click" data-href="#/invoices/${r.invoice_id}"><td><a class="mono" href="#/invoices/${r.invoice_id}">${r.invoice_id}</a></td><td>${r.invoice_type}</td><td>${r.received_date}</td><td class="num">${money(r.billed_total)}</td><td class="num">${money(r.expected_total)}</td><td>${badge(r.decision)}</td><td>${badge(r.status)}</td></tr>`)}</tbody></table>` : html`<p class="muted">Not invoiced yet.</p>`}</div>`);
  bindRowLinks();
}

// ------------------------------------------------------------------ carriers
async function viewCarriers(rest, params) {
  if (rest[0]) return viewCarrierDetail(rest[0], params);
  const o = await dsApi("/overview");
  const total = o.scorecard.reduce((s, r) => s + Number(r.overbilled_amount), 0);
  render(html`
    <div class="page-head"><div><h1>Carriers</h1><div class="sub">${o.scorecard.length} carriers · ${money(total)} overbilled in total. Click a carrier for its rate cards and accessorial contracts.</div></div>
      <a class="btn ghost" href="/files/${o.name}/reports/carrier_scorecard.csv" target="_blank">carrier_scorecard.csv</a></div>
    <div class="card" style="padding:6px 8px">${scorecardTable(o.scorecard)}</div>`);
  bindRowLinks();
}

async function viewCarrierDetail(id, params) {
  const d = await dsApi(`/carriers/${encodeURIComponent(id)}`);
  const c = d.carrier;
  const sc = d.scorecard || {};
  const card = params.get("card") || (d.rate_cards[0] || {}).rate_card_id;
  render(html`
    <div class="page-head"><div>
      <div class="muted"><a href="#/carriers">Carriers</a> /</div>
      <h1>${c.carrier_name} <span class="muted mono" style="font-weight:400">${c.carrier_id}</span></h1>
      <div class="sub">SCAC <code>${c.scac}</code> · ${c.carrier_tier} · ${c.home_city} · dispute window ${c.dispute_window_days} days · terms ${c.payment_terms_days} days · ${badge(c.status)}</div>
    </div><a class="btn ghost" href="#/exceptions?carrier=${c.carrier_id}">Exceptions for this carrier →</a></div>
    <div class="tiles">
      <div class="tile"><div class="label">Invoices</div><div class="value">${int(sc.invoices)}</div><div class="note">${pct(sc.clean_invoice_rate)} clean</div></div>
      <div class="tile"><div class="label">Billed</div><div class="value">${moneyK(sc.billed_amount || 0)}</div><div class="note">contract ${moneyK(sc.expected_amount || 0)}</div></div>
      <div class="tile"><div class="label">Overbilled</div><div class="value">${moneyK(sc.overbilled_amount || 0)}</div><div class="note">${int(sc.disputed_invoices)} disputed · ${int(sc.rejected_invoices)} rejected</div></div>
      <div class="tile"><div class="label">Credited</div><div class="value">${moneyK(sc.credited_amount || 0)}</div><div class="note">${int(sc.over_credit_notes)} over-credit notes flagged</div></div>
    </div>
    <div class="grid g2">
      <div class="card"><h2>Rate card versions</h2><div class="table-wrap"><table><thead><tr><th>Rate card</th><th>Effective</th><th class="num">Fuel %</th><th class="num">Dim divisor</th><th class="num">Lanes</th><th>Status</th></tr></thead>
        <tbody>${d.rate_cards.map((r) => html`<tr class="click ${r.rate_card_id === card ? "hl" : ""}" data-href="#/carriers/${c.carrier_id}?card=${r.rate_card_id}"><td class="mono">${r.rate_card_id}</td><td>${r.effective_from} → ${r.effective_to}</td><td class="num">${pct(r.fuel_surcharge_pct, 2)}</td><td class="num">${r.dim_divisor}</td><td class="num">${r.lanes}</td><td>${badge(r.status)}</td></tr>`)}</tbody></table></div></div>
      <div class="card"><h2>Exceptions by root cause</h2>${d.exceptions_by_type.length ? hbars(d.exceptions_by_type.map((r) => ({ label: r.exception_type, value: r.n, extra: `variance ${money(r.variance)}` })), { href: (i) => `#/exceptions?carrier=${c.carrier_id}&type=${i.label}` }) : html`<p class="muted">No exceptions.</p>`}</div>
    </div>
    <div class="card"><div class="card-head"><h2>Accessorial contracts</h2><span class="muted">contracted amount vs public tariff</span></div><div class="table-wrap"><table><thead><tr><th>Rate card</th><th>Code</th><th>Accessorial</th><th>Basis</th><th class="num">Contracted</th><th class="num">Tariff</th></tr></thead>
      <tbody>${d.accessorials.filter((a) => a.rate_card_id === card).map((a) => html`<tr><td class="mono">${a.rate_card_id}</td><td class="mono">${a.accessorial_code}</td><td>${a.accessorial_name}</td><td>${a.charge_basis}</td><td class="num">${money(a.contracted_amount)}</td><td class="num muted">${money(a.default_tariff_amount)}</td></tr>`)}</tbody></table></div></div>
    <div class="card"><div class="card-head"><h2>Rate lines · <span class="mono">${card}</span></h2>
      <form class="filters" id="rl-filter" style="margin:0"><select name="service" aria-label="Service level"><option value="">all services</option>${["STANDARD", "EXPEDITED", "GUARANTEED"].map((s) => html`<option>${s}</option>`)}</select></form></div>
      <div id="rate-lines" class="loading">Loading…</div></div>`);
  bindRowLinks();
  const load = async (page = 1) => {
    const svc = $("#rl-filter [name=service]").value;
    const q = new URLSearchParams({ rate_card_id: card, page, size: 60 });
    if (svc) q.set("service", svc);
    const r = await dsApi(`/rate-lines?${q}`);
    const pages = Math.max(1, Math.ceil(r.total / r.size));
    $("#rate-lines").className = "";
    $("#rate-lines").innerHTML = html`<div class="table-wrap"><table><thead><tr><th>Lane</th><th>Origin → destination</th><th>Service</th><th>Tier</th><th class="num">Tier range lb</th><th class="num">Rate / cwt</th><th class="num">Min charge</th></tr></thead>
      <tbody>${r.rows.map((x) => html`<tr><td class="mono">${x.lane_id}</td><td>${x.origin} → ${x.destination}</td><td>${x.service_level}</td><td>${x.weight_tier}</td><td class="num">${int(x.tier_min_lb)}–${int(x.tier_max_lb)}</td><td class="num">${money(x.rate_per_cwt)}</td><td class="num">${money(x.min_charge)}</td></tr>`)}</tbody></table></div>
      <div class="pager"><button class="btn ghost small" data-p="${r.page - 1}" ${r.page <= 1 ? raw("disabled") : ""}>← Prev</button><span>Page ${r.page} of ${pages} · ${int(r.total)} lines</span><button class="btn ghost small" data-p="${r.page + 1}" ${r.page >= pages ? raw("disabled") : ""}>Next →</button></div>`.__raw;
    $$("#rate-lines [data-p]").forEach((b) => b.addEventListener("click", () => load(Number(b.dataset.p))));
  };
  if (card) {
    $("#rl-filter [name=service]").addEventListener("change", () => load(1));
    await load(1);
  } else {
    $("#rate-lines").textContent = "No rate cards.";
  }
}

// ------------------------------------------------------------------ calculator
const FLAGS = [["liftgate_used", "Liftgate used"], ["residential_delivery", "Residential delivery"], ["inside_delivery", "Inside delivery"],
  ["appointment_required", "Appointment required"], ["limited_access", "Limited access"], ["hazmat", "Hazmat shipment"]];

async function viewCalculator(rest, params) {
  const f = await filterOptions();
  render(html`
    <div class="page-head"><div><h1>Rate calculator</h1>
      <div class="sub">The contractual expected charge, step by step, computed by the same <code>freight_audit.rating</code> functions the audit uses.</div></div></div>
    <div class="grid g-side">
      <div class="card">
        <form id="load-shp" class="filters" style="margin-bottom:14px">
          <input type="search" name="sid" placeholder="Load shipment, e.g. SHP-2026-000312" value="${params.get("shipment") || ""}" style="flex:1" aria-label="Shipment id">
          <button class="btn small" type="submit">Load</button>
        </form>
        <div id="shp-note" class="muted" style="font-size:12.5px;margin:-6px 0 10px"></div>
        <form id="calc" class="form-grid">
          <label class="full">Carrier<select name="carrier_id">${f.carriers.map((c) => html`<option value="${c.carrier_id}">${c.carrier_id} ${c.carrier_name}</option>`)}</select></label>
          <label class="full">Lane<select name="lane_id"></select></label>
          <label>Service<select name="service_level"><option>STANDARD</option><option>EXPEDITED</option><option>GUARANTEED</option></select></label>
          <label>Ship date<input type="date" name="ship_date" value="2026-06-15" min="2026-01-01" max="2026-12-31"></label>
          <label>Pieces<input type="number" name="pieces" value="4" min="1" max="1000"></label>
          <label>Actual weight (lb)<input type="number" name="actual_weight_lb" value="1850" min="0" step="0.1"></label>
          <label>Length (in)<input type="number" name="length_in" value="48" min="1"></label>
          <label>Width (in)<input type="number" name="width_in" value="40" min="1"></label>
          <label>Height (in)<input type="number" name="height_in" value="50" min="1"></label>
          <label>Wait at delivery (min)<input type="number" name="wait_minutes" value="0" min="0" max="1440"></label>
          <div class="full"><div style="font-size:12.5px;color:var(--text-2);margin-bottom:4px">Delivery evidence</div>
            <div class="checks">${FLAGS.map(([k, l]) => html`<label><input type="checkbox" name="${k}"> ${l}</label>`)}</div></div>
        </form>
      </div>
      <div id="quote"><div class="card loading">Pick inputs to see the quote.</div></div>
    </div>`);
  const form = $("#calc");
  const carrierSel = form.carrier_id;
  const loadLanes = async (keep) => {
    const opt = await dsApi(`/rate-options?carrier=${encodeURIComponent(carrierSel.value)}`);
    form.lane_id.innerHTML = opt.lanes.map((l) => `<option value="${esc(l.lane_id)}">${esc(l.lane_id)} · ${esc(l.origin_city)}, ${esc(l.origin_state)} → ${esc(l.dest_city)}, ${esc(l.dest_state)} (${l.distance_miles} mi)</option>`).join("");
    if (keep) form.lane_id.value = keep;
  };
  let timer;
  const recalc = () => { clearTimeout(timer); timer = setTimeout(runQuote, 200); };
  async function runQuote() {
    const fd = new FormData(form);
    const evidence = { wait_minutes: fd.get("wait_minutes") || 0 };
    FLAGS.forEach(([k]) => { evidence[k] = fd.get(k) === "on"; });
    const body = Object.fromEntries(["carrier_id", "lane_id", "service_level", "ship_date", "pieces", "length_in", "width_in", "height_in", "actual_weight_lb"].map((k) => [k, fd.get(k)]));
    body.evidence = evidence;
    try {
      const q = await dsApi("/quote", body);
      $("#quote").innerHTML = quoteView(q).__raw;
    } catch (e) {
      $("#quote").innerHTML = errorBox(e).__raw;
    }
  }
  carrierSel.addEventListener("change", async () => { await loadLanes(); recalc(); });
  form.addEventListener("input", recalc);
  form.addEventListener("change", recalc);
  $("#load-shp").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const sid = ev.target.sid.value.trim();
    if (!sid) return;
    try {
      const p = await dsApi(`/shipments/${encodeURIComponent(sid)}/quote-input`);
      carrierSel.value = p.carrier_id;
      await loadLanes(p.lane_id);
      ["service_level", "ship_date", "pieces", "length_in", "width_in", "height_in", "actual_weight_lb"].forEach((k) => { form[k].value = p[k]; });
      form.wait_minutes.value = p.evidence.wait_minutes;
      FLAGS.forEach(([k]) => { form[k].checked = !!p.evidence[k]; });
      $("#shp-note").innerHTML = html`Loaded <a class="mono" href="#/shipments/${p.shipment_id}">${p.shipment_id}</a> using ${p.measurement_source} measurement <span class="mono">${p.measurement_id}</span>${p.has_delivery_record ? "" : " (no delivery record yet)"}. Compare with its <a href="#/shipments/${p.shipment_id}">invoices</a>.`.__raw;
      runQuote();
    } catch (e) {
      $("#shp-note").innerHTML = html`<span class="bad-icon">${e.message}</span>`.__raw;
    }
  });
  await loadLanes();
  if (params.get("shipment")) $("#load-shp").requestSubmit(); else runQuote();
}

function quoteView(q) {
  const steps = html`<ol class="steps">${q.steps.map((s) => html`<li class="${s.ok === false ? "fail" : ""}"><div><strong>${s.title}</strong><span class="rule">${s.rule}</span><div class="muted mono" style="font-size:12.5px">${s.detail}</div></div></li>`)}</ol>`;
  if (!q.ok) return html`<div class="card"><div class="error-box">${q.error}</div>${steps}</div>`;
  return html`
    <div class="tiles" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">
      <div class="tile"><div class="label">Expected total</div><div class="value">${money(q.total)}</div><div class="note">${q.rate_card.rate_card_id}</div></div>
      <div class="tile"><div class="label">Billable weight</div><div class="value">${q.billable_weight_lb} lb</div><div class="note">dim ${q.dim_weight_lb} lb</div></div>
      <div class="tile"><div class="label">Weight tier</div><div class="value">${q.weight_tier}</div><div class="note">fuel ${pct(q.rate_card.fuel_surcharge_pct, 2)} · divisor ${q.rate_card.dim_divisor}</div></div>
    </div>
    <div class="card"><h2>Expected invoice lines</h2><div class="table-wrap"><table><thead><tr><th>Line</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>
      <tbody>${q.lines.map((l) => html`<tr><td>${l.line_type}${l.code ? html` <span class="muted">${l.code} ${l.description}</span>` : ""}</td><td class="num">${l.quantity}</td><td>${l.unit}</td><td class="num">${l.rate}</td><td class="num">${money(l.amount)}</td></tr>`)}
      <tr class="total-row"><td colspan="4">Expected total</td><td class="num">${money(q.total)}</td></tr></tbody></table></div>
      <p class="muted" style="margin-top:8px">A billed line within ±${q.tolerances.line_tolerance} of these amounts is accepted as rounding; overbilling below ${q.tolerances.waive_threshold} is waived, larger overbilling is disputed.</p></div>
    <div class="card"><h2>How it was computed</h2>${steps}</div>
    <div class="card"><h2>Accessorial check</h2><div class="table-wrap"><table><thead><tr><th>Code</th><th>Evidence rule</th><th class="num">Evidenced qty</th><th class="num">Contracted</th><th>Payable?</th></tr></thead>
      <tbody>${q.accessorials.map((a) => html`<tr><td><span class="mono">${a.code}</span><br><span class="muted">${a.name}</span></td><td class="mono muted" style="font-size:12px">${a.evidence_rule}</td><td class="num">${a.evidenced_qty}</td><td class="num">${a.contracted_amount === null ? html`<span class="muted">not contracted</span>` : money(a.contracted_amount)}</td>
        <td>${a.billable ? html`<span class="badge good" data-icon="✓ ">${money(a.amount)}</span>` : html`<span class="muted">${a.reason}</span>`}</td></tr>`)}</tbody></table></div></div>`;
}

// ------------------------------------------------------------------ validation
async function viewValidation(rest, params) {
  const v = await dsApi("/validation");
  const cat = params.get("category") || "";
  const status = params.get("status") || "";
  const rows = v.checks.filter((c) => (!cat || c.category === cat) && (!status || c.status === status));
  const cats = Object.keys(v.by_category);
  render(html`
    <div class="page-head"><div><h1>Validation</h1>
      <div class="sub">${badge(v.overall)} ${v.checks_total - v.checks_failed} of ${v.checks_total} integrity and business-rule checks passed. Checks with expected violations pass only when the violations are exactly the labelled cases.</div></div>
      <a class="btn ghost" href="/files/${state.ds}/reports/validation_summary.md" target="_blank">validation_summary.md</a></div>
    <div class="card"><h2>By category</h2>${hbars(cats.map((c) => ({ label: c, value: v.by_category[c].PASS + v.by_category[c].FAIL, extra: `${v.by_category[c].PASS} pass, ${v.by_category[c].FAIL} fail` })), { href: (i) => `#/validation?category=${i.label}`, fmt: (n) => `${n} checks` })}</div>
    <div class="card">
      <form class="filters" id="vf">
        <select name="category" aria-label="Category"><option value="">Category: all</option>${cats.map((c) => html`<option ${c === cat ? raw("selected") : ""}>${c}</option>`)}</select>
        <select name="status" aria-label="Status"><option value="">Status: all</option>${["PASS", "FAIL"].map((s) => html`<option ${s === status ? raw("selected") : ""}>${s}</option>`)}</select>
        <span class="muted" style="margin-left:auto">${rows.length} checks</span>
      </form>
      <div class="table-wrap"><table><thead><tr><th>Check</th><th>Category</th><th>Status</th><th class="num">Violations</th><th class="num">Expected</th><th>Description</th></tr></thead>
        <tbody>${rows.map((c) => html`<tr class="${c.status === "FAIL" ? "bad" : ""}"><td class="mono">${c.check_id}</td><td>${c.category}</td><td>${badge(c.status)}</td><td class="num">${int(c.violations)}</td><td class="num">${int(c.expected_violations)}</td>
          <td class="wrap">${c.description}${c.samples && c.samples.length ? html`<details><summary class="muted">${c.samples.length} sample(s)</summary><code style="display:block;white-space:pre-wrap">${c.samples.map((s) => (typeof s === "string" ? s : JSON.stringify(s))).join("\n")}</code></details>` : ""}</td></tr>`)}</tbody></table></div>
    </div>`);
  $$("#vf select").forEach((s) => s.addEventListener("change", () => {
    const p = new URLSearchParams();
    new FormData($("#vf")).forEach((x, k) => x && p.set(k, x));
    go("validation", p);
  }));
}

// ------------------------------------------------------------------ SQL console
const SAMPLE_SQL = [
  ["Why was each line flagged?", "SELECT exception_id, invoice_line_id, exception_type, status, explanation\nFROM audit_exception ORDER BY exception_id LIMIT 20"],
  ["History of one dispute", "SELECT event_seq, from_status, to_status, event_at, actor_role, note\nFROM exception_event WHERE exception_id = 'FEX-2026-000006'"],
  ["Credits vs approved disputes", "SELECT c.credit_note_id, e.exception_id, e.approved_amount, c.credit_amount, c.excess_amount, c.status\nFROM credit_note c JOIN audit_exception e USING (exception_id)\nWHERE c.status <> 'APPLIED'"],
  ["Overbilling by carrier", "SELECT f.carrier_id, COUNT(*) AS exceptions, ROUND(SUM(e.variance_amount), 2) AS variance\nFROM audit_exception e JOIN freight_invoice f USING (invoice_id)\nWHERE e.variance_amount > 0\nGROUP BY f.carrier_id ORDER BY variance DESC"],
  ["Dim weight governs", "SELECT measurement_id, actual_weight_lb, dim_weight_lb, billable_weight_lb\nFROM weight_measurement WHERE dim_weight_lb > actual_weight_lb\nORDER BY dim_weight_lb - actual_weight_lb DESC LIMIT 20"],
];

async function viewSql() {
  const schema = await dsApi("/schema");
  const last = store.get("sql") || SAMPLE_SQL[0][1];
  render(html`
    <div class="page-head"><div><h1>SQL console</h1><div class="sub">Read-only SQLite over <code>${state.ds}/data/sql/freight_audit.sqlite</code>. Only SELECT is allowed (authorizer-enforced), max 1,000 rows, 5 s.</div></div></div>
    <div class="grid g-side">
      <div class="card"><h2>Tables</h2><div class="schema-list">${schema.tables.map((t) => html`
        <details><summary><span class="mono">${t.name}</span><span class="muted">${int(t.rows)}</span></summary>
          <div class="muted" style="font-size:12px;margin:4px 0">${t.layer} · ${t.desc}</div>
          <ul>${t.columns.map((c) => html`<li><span class="mono">${c.name}</span> <span class="muted">${c.type}${c.fk ? " → " + c.fk : ""}</span></li>`)}</ul></details>`)}</div></div>
      <div>
        <div class="card sql-box">
          <textarea id="sql" spellcheck="false" aria-label="SQL query">${last}</textarea>
          <div class="chips">${SAMPLE_SQL.map(([l], i) => html`<button class="chip" type="button" data-i="${i}">${l}</button>`)}</div>
          <div style="display:flex;gap:8px;align-items:center"><button class="btn" id="run-sql">Run</button><button class="btn ghost" id="csv-sql" disabled>Download CSV</button><span class="muted" id="sql-meta">Ctrl+Enter to run</span></div>
        </div>
        <div id="sql-out"></div>
      </div>
    </div>`);
  let lastResult = null;
  const run = async () => {
    const sql = $("#sql").value;
    store.set("sql", sql);
    $("#sql-meta").textContent = "Running…";
    try {
      const r = await dsApi("/sql", { sql });
      lastResult = r;
      $("#csv-sql").disabled = false;
      $("#sql-meta").textContent = `${r.rows.length}${r.truncated ? "+ (truncated)" : ""} rows · ${r.elapsed_ms} ms`;
      $("#sql-out").innerHTML = html`<div class="card" style="padding:6px 8px"><div class="table-wrap" style="max-height:560px"><table><thead><tr>${r.columns.map((c) => html`<th>${c}</th>`)}</tr></thead>
        <tbody>${r.rows.map((row) => html`<tr>${row.map((x) => html`<td class="sql-cell ${typeof x === "number" ? "num" : ""}" title="${x === null ? "" : String(x).length > 60 ? x : ""}">${x === null ? html`<span class="muted">NULL</span>` : x}</td>`)}</tr>`)}</tbody></table></div></div>`.__raw;
    } catch (e) {
      lastResult = null;
      $("#csv-sql").disabled = true;
      $("#sql-meta").textContent = "";
      $("#sql-out").innerHTML = errorBox(e).__raw;
    }
  };
  $("#run-sql").addEventListener("click", run);
  $("#sql").addEventListener("keydown", (ev) => { if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") { ev.preventDefault(); run(); } });
  $$(".chip[data-i]").forEach((b) => b.addEventListener("click", () => { $("#sql").value = SAMPLE_SQL[b.dataset.i][1]; run(); }));
  $("#csv-sql").addEventListener("click", () => {
    if (!lastResult) return;
    const q = (x) => (x === null ? "" : /[",\n]/.test(String(x)) ? `"${String(x).replace(/"/g, '""')}"` : String(x));
    const text = [lastResult.columns.map(q).join(","), ...lastResult.rows.map((r) => r.map(q).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    a.download = "query.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  run();
}

// ------------------------------------------------------------------ rules
async function viewRules() {
  const m = state.meta || (state.meta = await api("/api/meta"));
  const p = m.policy;
  render(html`
    <div class="page-head"><div><h1>Rules &amp; policy</h1><div class="sub">Read live from <code>freight_audit/config.py</code> and <code>policy.py</code>. The generator's labels and the audit's verdicts both derive from these.</div></div></div>
    <div class="grid g2">
      <div class="card"><h2>Rating (expected charge)</h2>
        <ol class="steps">
          <li><div><strong>Authoritative weight</strong><span class="rule">W1</span><div class="muted">Latest CARRIER_REWEIGH, else latest SHIPPER_DECLARED.</div></div></li>
          <li><div><strong>Dimensional weight</strong><span class="rule">R-WGT-01</span><div class="muted">ceil(pieces × L × W × H / divisor); divisor from the rate card.</div></div></li>
          <li><div><strong>Billable weight</strong><div class="muted">max(actual, dimensional), capped at ${p.max_billable_lb} lb; weight tolerance ±${p.weight_tolerance_lb} lb.</div></div></li>
          <li><div><strong>Tier</strong><span class="rule">R-WGT-02</span><div class="muted">Lower bound inclusive, upper exclusive.</div></div></li>
          <li><div><strong>Base</strong><span class="rule">R1</span><div class="muted">max(min charge, round(weight / 100 × rate per cwt, 2)), half-up.</div></div></li>
          <li><div><strong>Fuel</strong><span class="rule">R-FSC-01</span><div class="muted">round(base × fuel %, 2); accessorials are not fuel-bearing.</div></div></li>
          <li><div><strong>Accessorials</strong><span class="rule">R-ACC-01/02</span><div class="muted">Payable only when contracted on the valid card AND evidenced; detention hours = ceil((wait − ${p.detention_free_minutes}) / 60).</div></div></li>
        </ol></div>
      <div class="card"><h2>Decision policy</h2><dl class="kv">
        <dt>Rounding tolerance</dt><dd>|billed − expected| ≤ ${p.line_tolerance} per line</dd>
        <dt>Waive threshold</dt><dd>overbilling &lt; ${p.waive_threshold} is waived</dd>
        <dt>Manager review</dt><dd>disputes ≥ ${p.manager_review_threshold} need an operations manager</dd>
        <dt>Invoice decision</dt><dd>REJECT if an invoice-level rule fires; DISPUTE if any line is overbilled by ≥ ${p.waive_threshold}; otherwise APPROVE</dd>
        <dt>Underbilling</dt><dd>accepted (closed), never disputed</dd></dl>
        <h3>Weight tiers</h3>
        <table><thead><tr><th>Tier</th><th class="num">From lb (incl.)</th><th class="num">To lb (excl.)</th></tr></thead><tbody>${m.weight_tiers.map((t) => html`<tr><td>${t.tier}</td><td class="num">${int(t.min_lb)}</td><td class="num">${int(t.max_lb)}</td></tr>`)}</tbody></table></div>
    </div>
    <div class="card"><h2>Exception taxonomy</h2><div class="table-wrap"><table><thead><tr><th>Exception type</th><th>Rule</th><th>Level</th><th>Effect</th></tr></thead>
      <tbody>${m.exception_types.map((t) => html`<tr><td><a href="#/exceptions?type=${t.type}">${t.type}</a></td><td class="mono">${t.rule_id}</td><td>${t.level}</td>
        <td class="muted">${t.level === "INVOICE" ? "whole invoice rejected" : t.level === "CREDIT" ? "carrier credit note does not match the approved dispute" : "line disputed, waived or accepted by variance"}</td></tr>`)}</tbody></table></div></div>
    <div class="card"><h2>Accessorial catalog</h2><div class="table-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>Basis</th><th class="num">Tariff</th><th>Evidence required</th></tr></thead>
      <tbody>${m.accessorials.map((a) => html`<tr><td class="mono">${a.code}</td><td>${a.name}</td><td>${a.basis}</td><td class="num">${money(a.tariff)}</td><td class="mono muted" style="font-size:12px">${a.evidence}</td></tr>`)}</tbody></table></div></div>
    <div class="card"><h2>Lifecycle state machines</h2><p class="muted">State changes are appended as events; history is never overwritten. Validation checks every event against these transitions.</p>
      <div class="grid g2">${Object.entries(m.lifecycles).map(([ent, tr]) => html`<div><h3>${ent}</h3><table><tbody>${Object.entries(tr).map(([a, b]) => html`<tr><td class="mono nowrap">${a}</td><td>→</td><td class="mono">${b.join(", ")}</td></tr>`)}</tbody></table></div>`)}</div></div>`);
}

// ------------------------------------------------------------------ run pipeline
async function viewRun(rest, params) {
  const m = state.meta || (state.meta = await api("/api/meta"));
  const jobs = await api("/api/jobs");
  const sel = Number(params.get("job")) || (jobs[0] || {}).id;
  render(html`
    <div class="page-head"><div><h1>Run pipeline</h1><div class="sub">Runs the real command-line tool in the background and streams its output: exactly what you would type in a terminal.</div></div></div>
    <div class="grid g3">
      <form class="card" id="f-run">
        <h2>Generate &amp; audit</h2>
        <p class="muted">generate → audit → disputes &amp; credits → export → validate → evaluate</p>
        <div class="form-grid">
          <label>Scale<select name="scale">${Object.keys(m.scales).map((s) => html`<option ${s === "starter" ? raw("selected") : ""}>${s}</option>`)}</select></label>
          <label>Seed<input type="number" name="seed" value="${m.default_seed}"></label>
          <label>Carriers<input type="number" name="carriers" placeholder="preset" min="1"></label>
          <label>Shipments<input type="number" name="shipments" placeholder="preset" min="1"></label>
          <label>Invoices<input type="number" name="invoices" placeholder="preset" min="1"></label>
        </div>
        <p class="muted" style="font-size:12.5px;margin-top:8px">Starter ≈ 2 s, full ≈ 30 s. Default seed + preset volumes overwrite <code>output/&lt;scale&gt;</code> (deterministic, so the data is identical). Any other seed or volume writes a new dataset.</p>
        <button class="btn" type="submit">Run</button>
      </form>
      <form class="card" id="f-tests">
        <h2>Test suite</h2>
        <p class="muted">23 engine tests (hand-calculated rating cases, end-to-end, negative controls) plus the web tests.</p>
        <p><code>python -m unittest discover -s tests -v</code></p>
        <button class="btn" type="submit">Run tests</button>
      </form>
      <form class="card" id="f-repro">
        <h2>Reproducibility</h2>
        <p class="muted">Runs the pipeline twice with the same seed and compares the SHA-256 of every output file (and the committed manifest).</p>
        <label class="field">Scale<select name="scale">${Object.keys(m.scales).map((s) => html`<option>${s}</option>`)}</select></label>
        <p></p><button class="btn" type="submit">Check reproducibility</button>
      </form>
    </div>
    <div class="card">
      <div class="card-head"><h2>Jobs</h2><span class="muted">kept in memory until the server restarts</span></div>
      ${jobs.length ? html`<div class="table-wrap"><table><thead><tr><th>#</th><th>Job</th><th>Status</th><th class="num">Elapsed</th><th>Last output</th></tr></thead>
        <tbody>${jobs.map((j) => html`<tr class="click ${j.id === sel ? "hl" : ""}" data-href="#/run?job=${j.id}"><td>${j.id}</td><td>${j.title}</td><td>${badge(j.status)}</td><td class="num">${j.elapsed_s}s</td><td class="mono muted wrap" style="font-size:12px">${(j.log_tail || [])[0] || ""}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No jobs yet.</p>`}
      <div id="job-detail"></div>
    </div>`);
  bindRowLinks();
  const submit = (id, kind) => $(id).addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = { kind };
    new FormData(ev.target).forEach((v, k) => { if (v !== "") body[k] = v; });
    try {
      const j = await api("/api/jobs", body);
      watchJobs();
      go("run", new URLSearchParams({ job: j.id }));
    } catch (e) {
      alert(e.message);
    }
  });
  submit("#f-run", "run");
  submit("#f-tests", "tests");
  submit("#f-repro", "repro");
  if (sel) followJob(sel);
}

function followJob(id) {
  let from = 0;
  let lines = [];
  const box = () => $("#job-detail");
  const tick = async () => {
    let j;
    try { j = await api(`/api/jobs/${id}?from=${from}`); } catch { return; }
    if (!box()) return;
    lines = lines.concat(j.log);
    from = j.log_total;
    const done = !["queued", "running"].includes(j.status);
    box().innerHTML = html`<h3>Job ${j.id} · ${j.title}</h3>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">${badge(j.status)} <code>${j.command}</code> <span class="muted">${j.elapsed_s}s${j.returncode !== null ? ` · exit ${j.returncode}` : ""}</span>
      ${!done ? html`<button class="btn ghost small" id="cancel-job">Cancel</button>` : ""}
      ${done && j.status === "succeeded" && j.dataset ? html`<button class="btn small" id="open-ds">Open dataset ${j.dataset} →</button>` : ""}</div>
      <pre class="log" id="log">${lines.join("\n") || "starting…"}</pre>`.__raw;
    const log = $("#log");
    log.scrollTop = log.scrollHeight;
    const c = $("#cancel-job");
    if (c) c.addEventListener("click", () => api(`/api/jobs/${id}/cancel`, {}));
    const o = $("#open-ds");
    if (o) o.addEventListener("click", async () => { state.filtersCache = {}; await loadDatasets(j.dataset); go("overview"); });
    if (done) {
      state.pollers.forEach(clearInterval);
      state.pollers = [];
      if (j.dataset) { state.filtersCache = {}; await loadDatasets(); }
    }
  };
  tick();
  state.pollers.push(setInterval(tick, 700));
}

// Global indicator: a dot on the nav while any job runs.
let jobWatch = null;
function watchJobs() {
  if (jobWatch) return;
  const check = async () => {
    try {
      const jobs = await api("/api/jobs");
      const running = jobs.some((j) => ["queued", "running"].includes(j.status));
      $("#job-dot").hidden = !running;
      if (!running) { clearInterval(jobWatch); jobWatch = null; await loadDatasets(); }
    } catch { /* server gone */ }
  };
  check();
  jobWatch = setInterval(check, 1500);
}

// ------------------------------------------------------------------ boot
function initTheme() {
  const saved = store.get("theme");
  if (saved) document.documentElement.dataset.theme = saved;
  $("#theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set("theme", next);
  });
}

async function boot() {
  initTheme();
  try {
    await loadDatasets();
  } catch (e) {
    render(errorBox(e));
    return;
  }
  $("#dataset").addEventListener("change", (ev) => {
    state.ds = ev.target.value;
    store.set("ds", state.ds);
    const { parts } = parseHash();
    if (parts.length > 1 && parts[0] !== "run") go(parts[0]); else route();
  });
  window.addEventListener("hashchange", () => { route(); main().focus({ preventScroll: true }); window.scrollTo(0, 0); });
  watchJobs();
  route();
}
boot();
