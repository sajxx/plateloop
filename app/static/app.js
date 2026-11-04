"use strict";
/* License plate MLOps console. Plain JS, no build step. Talks only to the local server's /api. */

// ---------------------------------------------------------------- helpers
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const svgns = "http://www.w3.org/2000/svg";
function svg(tag, attrs) { const e = document.createElementNS(svgns, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; }

async function api(path, opts = {}) {
  const o = { ...opts, headers: { "X-PlateLoop": "1", ...(opts.headers || {}) } };
  if (opts.json !== undefined) { o.method = "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opts.json); delete o.json; }
  const r = await fetch("/api/" + path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
  return data;
}
function toast(msg, err) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toasts").append(t); setTimeout(() => t.remove(), err ? 7000 : 3800);
}
const CANCELLED = Symbol("cancelled");
async function act(btn, fn, okMsg) {
  const label = btn.textContent; btn.disabled = true; btn.textContent = "Working…";
  try { const r = await fn(); if (r === CANCELLED) return r; if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg); return r; }
  catch (e) { toast(e.message, true); }
  finally { btn.disabled = false; btn.textContent = label; }
}
const when = v => v == null ? null : (typeof v === "number" ? new Date(v * 1000) : new Date(v));
function ago(v) {
  const d = when(v); if (!d) return "—";
  const s = Math.max(0, (Date.now() - d) / 1000);
  if (s < 60) return Math.round(s) + "s ago"; if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400) return Math.round(s / 3600) + " h ago"; return Math.round(s / 86400) + " d ago";
}
function dur(a, b) {
  const s = Math.max(0, ((when(b) || new Date()) - when(a)) / 1000);
  const m = Math.floor(s / 60); return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : m ? `${m}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`;
}
const f2 = v => v == null || isNaN(v) ? "—" : Number(v).toFixed(2);
const f3 = v => v == null || isNaN(v) ? "—" : Number(v).toFixed(3);
const pc = v => v == null || isNaN(v) ? "—" : (v * 100).toFixed(1) + "%";

const KIND = {
  green: ["InService", "CREATE_COMPLETE", "UPDATE_COMPLETE", "OK", "Approved", "SUCCEEDED", "accepted", "accepted_reviewed", "accepted_nova_only", "done", "registered"],
  amber: ["Creating", "Updating", "Deleting", "SystemUpdating", "RollingBack", "UPDATE_IN_PROGRESS", "CREATE_IN_PROGRESS", "IN_PROGRESS", "RUNNING", "running", "PendingManualApproval", "pending", "INSUFFICIENT_DATA", "quarantined"],
  red: ["Failed", "FAILED", "ALARM", "Rejected", "failed", "ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_COMPLETE", "ABORTED", "TIMED_OUT", "STOPPED", "OutOfService"],
};
const PULSE = new Set(["Creating", "Updating", "Deleting", "SystemUpdating", "RollingBack", "IN_PROGRESS", "RUNNING", "running", "UPDATE_IN_PROGRESS", "CREATE_IN_PROGRESS"]);
const LABELS = { PendingManualApproval: "Awaiting approval", no_plate: "no plate", not_better: "not better", accepted_reviewed: "reviewed", accepted_nova_only: "accepted (Nova)", INSUFFICIENT_DATA: "no data yet", OK: "OK", IN_PROGRESS: "in progress", InService: "Running", Off: "Off" };
function pill(text, kindOverride) {
  let kind = kindOverride || Object.keys(KIND).find(k => KIND[k].includes(text)) || "";
  return h("span", { class: `pill ${kind} ${PULSE.has(text) ? "pulse" : ""}` }, LABELS[text] || String(text).replace(/_/g, " "));
}
function bar(frac, kind, indeterminate) {
  return h("div", { class: `bar ${kind || ""} ${indeterminate ? "ind" : ""}` }, h("i", { style: { width: indeterminate ? "" : Math.min(100, Math.max(0, frac * 100)) + "%" } }));
}
function kpi(v, label, extra) { return h("div", { class: "card kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, label), extra || null); }
function empty(msg) { return h("div", { class: "empty" }, msg); }

// boxes drawn over an image: boxes = [{box:[x1,y1,x2,y2], color, label, dash}]
function boxImage(src, boxes, size) {
  const wrap = h("div", { class: "imgbox" });
  const img = h("img", { src, loading: "lazy", alt: "" });
  const s = svg("svg", { preserveAspectRatio: "xMidYMid meet" });
  const draw = (w, hh) => {
    s.setAttribute("viewBox", `0 0 ${w} ${hh}`); s.replaceChildren();
    const sw = Math.max(w, hh) / 190;
    for (const b of boxes) {
      const [x1, y1, x2, y2] = b.box;
      s.append(svg("rect", { x: x1, y: y1, width: x2 - x1, height: y2 - y1, fill: "none", stroke: b.color, "stroke-width": sw, "stroke-dasharray": b.dash ? `${sw * 3} ${sw * 2}` : "" }));
      if (b.label) {
        const fs = sw * 4.6, tw = b.label.length * fs * .58 + fs * .8;
        s.append(svg("rect", { x: x1, y: Math.max(0, y1 - fs * 1.35), width: tw, height: fs * 1.35, fill: b.color }));
        const t = svg("text", { x: x1 + fs * .4, y: Math.max(fs, y1 - fs * .35), fill: "#fff", "font-size": fs, "font-weight": 600 }); t.textContent = b.label; s.append(t);
      }
    }
  };
  if (size) draw(size[0], size[1]);
  img.addEventListener("load", () => draw(size ? size[0] : img.naturalWidth, size ? size[1] : img.naturalHeight));
  wrap.append(img, s); return wrap;
}
const BLUE = "#2563eb", ORANGE = "#ea580c", GREEN = "#16a34a";

function openModal(node) { $("#modalbox").replaceChildren(node); $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; $("#modalbox").replaceChildren(); }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

// ---------------------------------------------------------------- charts
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
Chart.defaults.font.size = 11; Chart.defaults.color = "#78716c"; Chart.defaults.borderColor = "#f0eeec";
Chart.defaults.plugins.legend.labels.boxWidth = 10; Chart.defaults.plugins.legend.labels.usePointStyle = true;
const PALETTE = ["#2563eb", "#ea580c", "#16a34a", "#9333ea", "#64748b"];

// ---------------------------------------------------------------- pages / router
const ICONS = {
  home: "M3 11l9-8 9 8M5 10v10h14V10", scan: "M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M8 12h8",
  image: "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M8.5 9.5h.01", list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01", check: "M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2h9",
  refresh: "M21 12a9 9 0 01-15.5 6.2M3 12A9 9 0 0118.5 5.8M3 4v5h5M21 20v-5h-5", box: "M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
  pulse: "M3 12h4l3-8 4 16 3-8h4", chart: "M4 20V10M10 20V4M16 20v-8M22 20H2", term: "M4 17l6-6-6-6M12 19h8",
};
const PAGES = [
  { id: "overview", title: "Overview", icon: "home", render: pageOverview },
  { id: "detect", title: "Detect", icon: "scan", render: pageDetect },
  { id: "gallery", title: "Gallery", icon: "image", render: pageGallery },
  { id: "requests", title: "Requests", icon: "list", render: pageRequests },
  { id: "review", title: "Label review", icon: "check", render: pageReview },
  { id: "retrain", title: "Retraining", icon: "refresh", render: pageRetrain },
  { id: "models", title: "Models", icon: "box", render: pageModels },
  { id: "monitoring", title: "Monitoring", icon: "pulse", render: pageMonitoring },
  { id: "evaluation", title: "Evaluation", icon: "chart", render: pageEvaluation },
  { id: "logs", title: "Logs", icon: "term", render: pageLogs },
];
let cleanups = [], gen = 0;
function buildNav() {
  const nav = $("#nav");
  for (const p of PAGES) {
    const ico = svg("svg", { viewBox: "0 0 24 24" }); ico.append(svg("path", { d: ICONS[p.icon] }));
    nav.append(h("a", { href: "#/" + p.id, "data-id": p.id }, ico, p.title, p.id === "review" ? h("span", { class: "nav-badge", id: "reviewBadge", hidden: true }) : null));
  }
}
async function route() {
  cleanups.forEach(f => f()); cleanups = []; closeModal();
  const mine = ++gen, live = () => mine === gen;       // a page that was left must never touch the screen again
  const ctx = {
    live,
    every(fn, ms) { const id = setInterval(() => { if (live()) fn().catch?.(() => {}); }, ms); cleanups.push(() => clearInterval(id)); return id; },
    chart(canvas, cfg) { if (!live()) return null; const c = new Chart(canvas, cfg); cleanups.push(() => c.destroy()); return c; },
    onLeave(fn) { cleanups.push(fn); },
    actions: () => live() ? $("#actions") : document.createElement("div"),
  };
  const id = (location.hash.replace("#/", "") || "overview");
  const page = PAGES.find(p => p.id === id) || PAGES[0];
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.id === page.id));
  $("#title").textContent = page.title; $("#actions").replaceChildren();
  const root = h("div", {}, h("div", { class: "empty" }, h("span", { class: "spinner" })));
  $("#page").replaceChildren(root);                     // every page renders into its own element
  try { await page.render(root, ctx); } catch (e) { if (live()) root.replaceChildren(h("div", { class: "banner red" }, "Could not load this page: " + e.message)); }
}
window.addEventListener("hashchange", route);

async function refreshSide() {
  try {
    const d = await api("overview");
    const foot = $("#sidefoot");
    foot.replaceChildren(h("div", {}, h("span", {}, "Endpoint"), pill(d.endpoint.status)), h("div", {}, h("span", {}, "Model"), h("b", {}, d.model_version)),
      h("div", {}, h("span", {}, "Account"), h("span", {}, "…" + d.account.slice(-4))), h("div", {}, h("span", {}, "Region"), h("span", {}, d.region)));
    const b = $("#reviewBadge"); if (b) { b.hidden = !d.quarantine; b.textContent = d.quarantine; }
  } catch (e) { /* server restarting */ }
}

// ---------------------------------------------------------------- Overview
async function pageOverview(root, ctx) {
  const draw = async () => {
    const d = await api("overview");
    const ep = d.endpoint, busy = ["Creating", "Updating", "Deleting", "SystemUpdating", "RollingBack"].includes(ep.status);
    const c = d.counters, th = d.thresholds;
    const startBtn = h("button", { class: "btn primary", onclick: e => act(e.target, async () => {
      if (!confirm("Start the detector endpoint?\n\nIt takes 5–10 minutes and costs about $0.10 per hour while running. It switches itself off after 30 idle minutes.")) return CANCELLED;
      await api("endpoint/start", { json: {} }); draw();
    }, "Endpoint is starting") }, "Start endpoint");
    const stopBtn = h("button", { class: "btn danger", onclick: e => act(e.target, async () => { await api("endpoint/stop", { json: {} }); draw(); }, "Endpoint is stopping") }, "Stop endpoint");
    const epCard = h("div", { class: "card" },
      h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Detector endpoint"), pill(ep.status), h("span", { class: "sp" }),
        ep.status === "Off" ? startBtn : ep.status === "InService" ? stopBtn : null),
      busy ? h("div", { class: "mt" }, bar(0, "", true), h("div", { class: "small muted", style: { marginTop: "6px" } },
        `${ep.status === "Deleting" ? "Shutting down" : ep.status === "Creating" ? "Starting" : "Updating"}… ${ep.created ? "elapsed " + dur(ep.created) : ""}. This page updates by itself.`)) : null,
      ep.failure ? h("div", { class: "banner red mt" }, ep.failure) : null,
      h("dl", { class: "mt" }, h("dt", {}, "Model version"), h("dd", {}, ep.version || d.model_version),
        h("dt", {}, "Instance"), h("dd", {}, "ml.m5.large (CPU)"),
        h("dt", {}, "Running since"), h("dd", {}, ep.status === "Off" ? "—" : ago(ep.created)),
        h("dt", {}, "Auto-shutdown"), h("dd", {}, h("select", { id: "idleSel", onchange: async e => { try { await api("endpoint/idle", { json: { minutes: +e.target.value } }); toast("Auto-shutdown updated"); draw(); } catch (err) { toast(err.message, true); } } },
          [[15, "after 15 idle minutes"], [30, "after 30 idle minutes"], [60, "after 1 idle hour"], [120, "after 2 idle hours"], [240, "after 4 idle hours"], [0, "never (keeps billing)"]].map(([v, t]) => h("option", { value: v, selected: v === ep.idle_minutes }, t))),
          h("div", { class: "small muted" }, ep.idle_minutes ? "Checked every 15 minutes; any request resets the clock." + (ep.last_activity ? ` Last request ${ago(ep.last_activity)}.` : "") : "You must stop it yourself.")),
        h("dt", {}, "Public API"), h("dd", { class: "mono", style: { wordBreak: "break-all" } }, d.api_url + "/predict")));
    const newLabels = c.new_labels || 0, spend = d.budget.actual || 0, lim = d.budget.limit || 20;
    const kpis = h("div", { class: "grid g4" },
      kpi(d.requests_total, "Images processed"), kpi(c.labels_accepted || 0, "Labels accepted"),
      kpi(d.quarantine, "Waiting for review", d.quarantine ? h("a", { href: "#/review", class: "small" }, "Review now →") : null),
      kpi(d.queues.labeling, "In labelling queue", d.queues.failed ? h("div", { class: "small", style: { color: "var(--red)" } }, d.queues.failed + " failed") : null));
    const rt = d.retrain, running = rt.status === "running";
    const retrainCard = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Retraining"),
      running ? pill("running") : pill(rt.outcome || "idle"), h("span", { class: "sp" }), h("a", { href: "#/retrain", class: "small" }, "Open →")),
      h("div", { class: "small muted mt" }, `New labels since the last run: ${newLabels} of ${th.new_label_count}`), bar(newLabels / th.new_label_count),
      h("div", { class: "small muted", style: { marginTop: "10px" } }, rt.run_id ? `Last run ${rt.run_id}, started ${ago(rt.started_at)}` : "No run yet"));
    const budgetCard = h("div", { class: "card" }, h("h2", {}, "Monthly budget"),
      h("div", { class: "row" }, h("div", { class: "kpi" }, h("div", { class: "v" }, "$" + spend.toFixed(2))), h("span", { class: "muted" }, `of $${lim.toFixed(0)}`)),
      bar(spend / lim, spend / lim > .8 ? "red" : spend / lim > .5 ? "amber" : "green"),
      h("div", { class: "small muted", style: { marginTop: "6px" } }, d.budget.forecast ? `Forecast $${d.budget.forecast.toFixed(2)}` : "AWS shows spend with a delay of several hours."));
    const stacks = h("div", { class: "card" }, h("h2", {}, "Deployed stacks"), h("table", {}, h("tbody", {},
      d.stacks.sort((a, b) => a.name.localeCompare(b.name)).map(s => h("tr", {}, h("td", {}, s.name.replace("plateloop-", "")), h("td", {}, pill(s.status)), h("td", { class: "muted small" }, ago(s.updated)))))));
    const alarms = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Alarms"), h("span", { class: "sp" }), h("a", { href: "#/monitoring", class: "small" }, "Open →")),
      h("table", { class: "mt" }, h("tbody", {}, d.alarms.map(a => h("tr", {}, h("td", {}, a.name.replace("plateloop-", "").replace(/-/g, " ")), h("td", { style: { textAlign: "right" } }, pill(a.state)))))));
    root.replaceChildren(h("div", { class: "grid" }, epCard, kpis, h("div", { class: "grid g3" }, retrainCard, budgetCard, alarms), stacks));
    return busy;
  };
  let busy = await draw();
  const loop = async () => { busy = await draw(); };
  ctx.every(loop, 5000);
}

// ---------------------------------------------------------------- Detect
async function idemKey(blob, fresh) {          // same bytes -> same key, so a repeat send cannot create a second request
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  const hex = [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 48);
  return "img-" + hex + (fresh ? "-" + Math.random().toString(36).slice(2, 8) : "");
}
const LABEL_TEXT = { accepted: "Both models agree: label accepted", accepted_nova_only: "Second model found a plate: label accepted", no_plate: "No plate in the image: accepted as a negative", quarantined: "Models disagree: waiting in Label review" };

function endpointStrip(ctx, onChange) {
  const el = h("div", { class: "card", style: { marginBottom: "14px" } });
  const state = { ep: { status: "…" } };
  setTimeout(() => draw(), 0);
  const start = e => act(e.target, async () => {
    if (!confirm("Start the detector endpoint?\n\nIt takes about 4–6 minutes and costs about $0.10 per hour while running.")) return CANCELLED;
    await api("endpoint/start", { json: {} }); await poll();
  }, "Endpoint is starting");
  function draw() {
    const ep = state.ep, busy = ["Creating", "Updating", "SystemUpdating", "RollingBack"].includes(ep.status);
    let msg = "", right = null, bar_ = null;
    if (ep.status === "Off") { msg = "The detector is switched off, so nothing can be analysed yet."; right = h("button", { class: "btn primary", onclick: start }, "Start endpoint"); }
    else if (busy) { msg = `Starting up… ${ep.created ? "elapsed " + dur(ep.created) : ""}. Detection unlocks by itself when it is ready, so there is no need to retry.`; bar_ = bar(0, "", true); }
    else if (ep.status === "…") msg = "Checking the detector…";
    else if (ep.status === "Deleting") msg = "The detector is shutting down.";
    else if (ep.status === "InService") {
      const idle = ep.idle_minutes;
      msg = idle ? `Ready. Switches itself off after ${idle} idle minutes${ep.last_activity ? " (last request " + ago(ep.last_activity) + ")" : ""}.` : "Ready. Automatic shutdown is off, so it keeps running (and billing) until you stop it.";
    } else msg = ep.status;
    el.replaceChildren(...[h("div", { class: "row" }, h("b", {}, "Detector"), pill(ep.status), h("span", { class: "muted small" }, msg), h("span", { class: "sp" }), right), bar_ ? h("div", { class: "mt" }, bar_) : null].filter(Boolean));
  }
  async function poll() {
    const ep = await api("endpoint"); if (!ctx.live()) return;
    const changed = ep.status !== state.ep.status; state.ep = ep; draw(); if (changed) onChange(ep);
  }
  return { el, state, poll, ready: () => state.ep.status === "InService" };
}

async function pageDetect(root, ctx) {
  const st = { img: null, name: "", gt: [], origW: 0, result: null, runs: [], sample: false, sending: false, fresh: false };
  const canvas = h("canvas", {}), overlay = svg("svg", { preserveAspectRatio: "none" });
  const view = h("div", { class: "imgbox", style: { display: "none" } }, canvas, overlay);
  const file = h("input", { type: "file", accept: "image/jpeg,image/png", hidden: true });
  const drop = h("div", { class: "drop", onclick: () => file.click() }, h("b", {}, "Drop a photo here"), h("div", { class: "small" }, "or click to choose · JPEG or PNG"));
  const sample = h("select", {}, h("option", { value: "" }, "Choose a sample image…"));
  const sl = { b: 1, blur: 0, noise: 0 };
  const sliderRow = (label, key, min, max, step, fmt) => {
    const out = h("span", { class: "mono" }, fmt(sl[key]));
    const inp = h("input", { type: "range", min, max, step, value: sl[key], oninput: e => { sl[key] = +e.target.value; out.textContent = fmt(sl[key]); schedule(); } });
    return h("div", { class: "slider" }, h("span", { class: "muted" }, label), inp, out);
  };
  const runBtn = h("button", { class: "btn primary", onclick: () => run().catch(e => toast(e.message, true)) }, "Detect plates");
  const why = h("div", { class: "small muted", id: "whyDisabled", style: { marginTop: "6px" } });
  const resetBtn = h("button", { class: "btn", onclick: () => { sl.b = 1; sl.blur = 0; sl.noise = 0; st.fresh = false; build(); paint(); } }, "Reset");
  const out = h("div", {}), banner = h("div", {});
  const saveBox = h("input", { type: "checkbox", id: "saveBox", checked: true });
  const saveNote = h("span", { class: "small muted", id: "saveNote" });
  const strip = endpointStrip(ctx, () => syncBtn());
  const syncSave = () => { saveBox.disabled = st.sample; if (st.sample) saveBox.checked = false;
    saveNote.textContent = st.sample ? "Golden-set images are never saved, so they cannot leak into training." : "Saved images feed monitoring and automatic labelling."; };
  function syncBtn() {
    const ready = strip.ready(), epst = strip.state.ep.status;
    const blocked = !st.img ? "Choose an image first." : st.sending ? "" : ready ? "" : epst === "…" ? "Checking the detector…" : epst === "Off" ? "Start the detector above first." : epst === "Deleting" ? "The detector is shutting down." : "Waiting for the detector to finish starting…";
    runBtn.disabled = !st.img || !ready || st.sending;
    runBtn.textContent = st.sending ? "Sending…" : "Detect plates";
    why.textContent = blocked;
  }
  let pending = false;
  const schedule = () => { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; paint(); }); } };

  function paint() {
    if (!st.img) return;
    const s = Math.min(1, 1600 / Math.max(st.img.naturalWidth, st.img.naturalHeight));
    canvas.width = Math.round(st.img.naturalWidth * s); canvas.height = Math.round(st.img.naturalHeight * s);
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.filter = `brightness(${sl.b}) blur(${sl.blur * s}px)`; g.drawImage(st.img, 0, 0, canvas.width, canvas.height); g.filter = "none";
    if (sl.noise > 0) {
      const d = g.getImageData(0, 0, canvas.width, canvas.height), px = d.data;
      for (let i = 0; i < px.length; i += 4) {
        const n = (Math.random() + Math.random() + Math.random() - 1.5) * 2 * sl.noise;
        px[i] += n; px[i + 1] += n; px[i + 2] += n;
      }
      g.putImageData(d, 0, 0);
    }
    overlay.setAttribute("viewBox", `0 0 ${canvas.width} ${canvas.height}`); drawBoxes();
  }
  function drawBoxes() {
    overlay.replaceChildren(); if (!canvas.width) return;
    const sw = Math.max(canvas.width, canvas.height) / 190, k = canvas.width / (st.origW || canvas.width);
    for (const b of st.gt) { const [x1, y1, x2, y2] = b.map(v => v * k); overlay.append(svg("rect", { x: x1, y: y1, width: x2 - x1, height: y2 - y1, fill: "none", stroke: GREEN, "stroke-width": sw, "stroke-dasharray": `${sw * 3} ${sw * 2}` })); }
    for (const d of st.result?.detections || []) {
      const [x1, y1, x2, y2] = d.box, fs = sw * 4.6, lab = (d.score * 100).toFixed(0) + "%";
      overlay.append(svg("rect", { x: x1, y: y1, width: x2 - x1, height: y2 - y1, fill: "none", stroke: BLUE, "stroke-width": sw }));
      overlay.append(svg("rect", { x: x1, y: Math.max(0, y1 - fs * 1.35), width: lab.length * fs * .6 + fs, height: fs * 1.35, fill: BLUE }));
      const t = svg("text", { x: x1 + fs * .4, y: Math.max(fs, y1 - fs * .35), fill: "#fff", "font-size": fs, "font-weight": 600 }); t.textContent = lab; overlay.append(t);
    }
  }
  function setImage(img, name, gt, origW, sample) {
    st.sample = !!sample; syncSave(); st.fresh = false;
    st.img = img; st.name = name; st.gt = gt || []; st.origW = origW || img.naturalWidth; st.result = null;
    view.style.display = "inline-block"; drop.style.display = "none"; out.replaceChildren(); banner.replaceChildren(); paint(); syncBtn();
  }
  function loadFile(f) { if (!f) return; const im = new Image(); im.onload = () => setImage(im, f.name, [], im.naturalWidth, false); im.src = URL.createObjectURL(f); }
  file.addEventListener("change", () => loadFile(file.files[0]));
  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); loadFile(e.dataTransfer.files[0]); });
  const golden = (await api("golden")).items;
  golden.forEach(g => sample.append(h("option", { value: g.file }, g.file.slice(0, 34))));
  sample.addEventListener("change", () => {
    const g = golden.find(x => x.file === sample.value); if (!g) return;
    const im = new Image(); im.onload = () => setImage(im, g.file, g.gt, g.width, true); im.src = `/api/image?key=golden/images/${encodeURIComponent(g.file)}`;
  });

  // ---- the tracker: shows every stage of a send as it happens
  function tracker(saved) {
    const names = ["Image prepared", "Sent to the detector", ...(saved ? ["Saved to the system", "Checked by the second model"] : ["Preview only: nothing is saved"])];
    const rows = names.map(n => ({ n, s: "waiting", note: "" })), box = h("div", { class: "card mt", id: "tracker" });
    let footer = null;
    const draw = () => box.replaceChildren(h("h2", {}, "Progress"), ...rows.map(r => h("div", { class: "row", style: { padding: "5px 0" } },
      h("span", { style: { width: "20px", textAlign: "center" } }, r.s === "running" ? h("span", { class: "spinner" }) : r.s === "done" ? h("b", { style: { color: "var(--green)" } }, "✓") : r.s === "failed" ? h("b", { style: { color: "var(--red)" } }, "✕") : h("span", { class: "muted" }, "○")),
      h("span", { class: r.s === "waiting" ? "muted" : "" }, r.n), h("span", { class: "sp" }), h("span", { class: "small muted", "data-note": "" }, r.note))), footer);
    draw();
    return { box, set(i, s, note) { rows[i].s = s; if (note != null) rows[i].note = note; draw(); }, link(node) { footer = node; draw(); },
      current() { const k = rows.findIndex(r => r.s === "running"); return k < 0 ? rows.findLastIndex(r => r.s === "done") + 1 : k; } };
  }
  async function pollLabel(id, T, i) {
    const t0 = Date.now();
    while (Date.now() - t0 < 150000 && ctx.live()) {
      const row = await api("request/" + id).catch(() => null);
      if (row && row.label_status && !["pending", "processing"].includes(row.label_status)) { T.set(i, "done", LABEL_TEXT[row.label_status] || row.label_status); return row.label_status; }
      T.set(i, "running", `Waiting for the second model… ${Math.round((Date.now() - t0) / 1000)} s`);
      await new Promise(r => setTimeout(r, 2000));
    }
    if (ctx.live()) T.set(i, "waiting", "Still labelling. It will show up in Requests when finished.");
  }

  async function run() {
    if (st.sending || !st.img) return;
    st.sending = true; syncBtn(); banner.replaceChildren();
    const saved = saveBox.checked, T = tracker(saved);
    out.replaceChildren(T.box);
    try {
      const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", .92));
      T.set(0, "done", `${canvas.width}×${canvas.height}, ${(blob.size / 1024).toFixed(0)} KB`);
      const key = saved ? await idemKey(blob, st.fresh) : null; st.fresh = false;
      T.set(1, "running", "waiting for the detector…");
      const fd = new FormData(); fd.append("file", blob, "image.jpg");
      const r = await api("detect?store=" + saved, { method: "POST", body: fd, headers: key ? { "X-Idempotency-Key": key } : {} });
      if (r.http_status === 503) {
        T.set(1, "failed", "detector offline"); st.result = null; drawBoxes(); await strip.poll();
        banner.replaceChildren(h("div", { class: "banner" }, "The detector went offline before it could answer. Nothing was saved, so you can simply send again once it is running.")); return;
      }
      if (r.http_status === 202) {                       // an identical request is already in flight (double click or retry)
        T.set(1, "running", "this exact image is already being processed…");
        for (let k = 0; k < 40; k++) { await new Promise(x => setTimeout(x, 1500)); const row = await api("request/" + r.image_id).catch(() => null); if (row && row.label_status !== "processing") { r.http_status = 200; Object.assign(r, row, { duplicate: true }); break; } }
      }
      if (r.http_status !== 200) throw new Error(r.error || "request failed (" + r.http_status + ")");
      st.result = r; drawBoxes();
      const n = r.detections.length;
      T.set(1, "done", r.duplicate ? "already processed earlier, showing the saved result" : `${n} plate${n === 1 ? "" : "s"} found in ${r.latency_ms} ms`);
      if (r.top_confidence == null) r.top_confidence = r.detections[0]?.score || 0;
      st.runs.unshift({ setting: `brightness ${sl.b.toFixed(2)} · blur ${sl.blur.toFixed(1)} · noise ${sl.noise}`, conf: r.top_confidence, n, ms: r.latency_ms });
      st.runs = st.runs.slice(0, 8);
      if (r.duplicate) banner.replaceChildren(h("div", { class: "banner", style: { background: "var(--accent-bg)", borderColor: "#bfdbfe", color: "var(--accent)" } },
        h("span", {}, "This exact image was already processed, so no new request was created."), h("span", { class: "sp" }),
        h("button", { class: "btn sm", onclick: () => { st.fresh = true; run().catch(e => toast(e.message, true)); } }, "Process again as a new request")));
      showResult(r, T.box);
      if (saved) {
        T.set(2, "done", `id ${r.image_id.slice(0, 14)}…`);
        T.link(h("div", { class: "small", style: { marginTop: "8px" } }, h("a", { href: "#/requests" }, "View it in Requests →"), "  ·  ", h("a", { href: "#/gallery" }, "or in the Gallery → Saved uploads")));
        const lab = await pollLabel(r.image_id, T, 3);
        if (lab) toast("Image labelled: " + (LABEL_TEXT[lab] || lab));
      }
    } catch (e) {
      const cur = T.current(); T.set(cur, "failed", e.message.slice(0, 90));
      banner.replaceChildren(h("div", { class: "banner red" }, "The send did not complete: " + e.message + ". Nothing was left half-saved. You can try again."));
      throw e;
    } finally { st.sending = false; syncBtn(); }
  }
  function showResult(r, trackerBox) {
    const s = r.stats || {};
    out.replaceChildren(...[trackerBox,
      h("div", { class: "grid g3 mt" }, kpi(r.detections.length, "Plates found"), kpi(r.detections.length ? pc(r.top_confidence) : "—", "Top confidence"), kpi(r.latency_ms + " ms", r.stored === false ? "Round trip to the model (not saved)" : "Round trip through the public API")),
      h("div", { class: "card mt" }, h("h2", {}, "Detections"), r.detections.length ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "Confidence"), h("th", {}, "Box (x1, y1, x2, y2)"))),
        h("tbody", {}, r.detections.map((d, i) => h("tr", {}, h("td", {}, i + 1), h("td", { style: { width: "45%" } }, h("div", { class: "row" }, h("span", { class: "mono" }, pc(d.score)), h("div", { style: { flex: 1 } }, bar(d.score, d.score > .7 ? "green" : "amber")))), h("td", { class: "mono" }, d.box.map(v => Math.round(v)).join(", ")))))) : empty("No plate found in this image.")),
      h("div", { class: "card mt" }, h("h2", {}, "Image details"), h("dl", {}, h("dt", {}, "Model version"), h("dd", {}, r.model_version), h("dt", {}, "Size sent"), h("dd", {}, `${r.width} × ${r.height}`),
        h("dt", {}, "Brightness"), h("dd", {}, f2(s.brightness)), h("dt", {}, "Sharpness score"), h("dd", {}, f2(s.blur_score)), h("dt", {}, "Request id"), h("dd", { class: "mono" }, r.image_id || "not saved"))),
      st.runs.length > 1 ? h("div", { class: "card mt" }, h("h2", {}, "Recent runs on this page"), h("div", { class: "small muted" }, "Make the picture darker, blurrier or noisier and watch the confidence fall: this is the kind of drift the monitoring alarms watch for."),
        h("table", { class: "mt" }, h("thead", {}, h("tr", {}, h("th", {}, "Settings"), h("th", {}, "Plates"), h("th", {}, "Top confidence"))),
          h("tbody", {}, st.runs.map(x => h("tr", {}, h("td", { class: "mono" }, x.setting), h("td", {}, x.n), h("td", {}, pc(x.conf))))))) : null].filter(Boolean));
  }
  function build() {
    const controls = h("div", {}, sliderRow("Brightness", "b", .1, 1.6, .05, v => v.toFixed(2)), sliderRow("Blur", "blur", 0, 8, .5, v => v.toFixed(1)), sliderRow("Noise", "noise", 0, 60, 2, v => String(v)));
    left.replaceChildren(h("div", { class: "card" }, drop, file, view, h("div", { class: "row mt" }, sample), h("h3", { class: "mt" }, "Simulate a worse camera"), controls,
      h("label", { class: "row small mt" }, saveBox, "Save this image to the system"), saveNote,
      h("div", { class: "row mt" }, runBtn, resetBtn, h("span", { class: "sp" }), st.gt.length ? h("span", { class: "legend" }, h("span", {}, h("i", { style: { background: GREEN } }), "true plate"), h("span", {}, h("i", { style: { background: BLUE } }), "detected")) : null), why));
    syncSave(); syncBtn();
  }
  const left = h("div", {});
  build();
  root.replaceChildren(strip.el, banner, h("div", { class: "grid g2" }, left, out));
  await strip.poll(); syncBtn();
  ctx.every(async () => { await strip.poll(); syncBtn(); }, 3000);
}

// ---------------------------------------------------------------- Gallery
const KIND_COLOR = { truth: GREEN, detection: BLUE };
async function pageGallery(root, ctx) {
  const COLS = [["golden", "Golden set"], ["train", "Training set"], ["labels", "Auto-labelled"], ["raw", "Saved uploads"], ["run", "Retraining data"]];
  const NOTE = { golden: "150 held-out images the model never trains on, with the true plate boxes (green).",
    train: "The 2,000 original images model v1 was trained on, with their labelled boxes (green).",
    labels: "Images labelled automatically or by review. Green boxes are what the next training run will use.",
    raw: "Every image sent through the live system, with the boxes the detector found (blue).",
    run: "The exact images and labels a retraining run used, mixed from original and new data." };
  const st = { col: "golden", page: 1, q: "", run: "", data: null, at: 0 };
  const tabs = h("div", { class: "row" }), note = h("div", { class: "muted small", style: { margin: "10px 0" } });
  const search = h("input", { type: "text", placeholder: "Search file name", oninput: e => { clearTimeout(search._t); search._t = setTimeout(() => { st.q = e.target.value; st.page = 1; load(); }, 300); } });
  const runSel = h("select", { hidden: true, onchange: e => { st.run = e.target.value; st.page = 1; load(); } });
  const grid = h("div", { class: "thumbs" }), pager = h("div", { class: "row", style: { justifyContent: "center", marginTop: "16px" } });
  const boxes = it => it.boxes.map(b => ({ box: b.box, color: KIND_COLOR[b.kind] || BLUE, label: b.score != null ? (b.score * 100).toFixed(0) + "%" : null }));
  const cap = it => it.status ? pill(it.status) : h("span", { class: "muted" }, `${it.boxes.length} plate${it.boxes.length === 1 ? "" : "s"}`);

  function viewer(i) {
    st.at = i; const it = st.data.items[i];
    const body = h("div", {}, h("div", { class: "row" }, h("h2", { style: { margin: 0, wordBreak: "break-all" } }, it.name), h("span", { class: "sp" }),
      h("span", { class: "muted small" }, `${(st.data.page - 1) * 48 + i + 1} of ${st.data.total}`),
      h("button", { class: "btn sm", disabled: i === 0, onclick: () => viewer(i - 1) }, "←"), h("button", { class: "btn sm", disabled: i === st.data.items.length - 1, onclick: () => viewer(i + 1) }, "→"),
      h("button", { class: "btn sm", onclick: closeModal }, "Close")),
      h("div", { class: "mt", style: { textAlign: "center" } }, boxImage(`/api/image?key=${encodeURIComponent(it.key)}&w=1100`, boxes(it), it.width ? [it.width, it.height] : null)),
      h("dl", { class: "mt" }, h("dt", {}, "Plates"), h("dd", {}, it.boxes.length), it.width ? [h("dt", {}, "Size"), h("dd", {}, `${it.width} × ${it.height}`)] : null,
        it.status ? [h("dt", {}, "Label status"), h("dd", {}, it.status.replace(/_/g, " "))] : null,
        it.boxes[0]?.score != null ? [h("dt", {}, "Detector confidence"), h("dd", {}, it.boxes.map(b => pc(b.score)).join(", "))] : null,
        h("dt", {}, "Stored at"), h("dd", { class: "mono", style: { wordBreak: "break-all" } }, it.key)));
    openModal(body);
  }
  const onKey = e => { if ($("#modal").hidden || !st.data) return; if (e.key === "ArrowRight" && st.at < st.data.items.length - 1) viewer(st.at + 1); if (e.key === "ArrowLeft" && st.at > 0) viewer(st.at - 1); };
  document.addEventListener("keydown", onKey); ctx.onLeave(() => document.removeEventListener("keydown", onKey));

  function render() {
    const d = st.data;
    tabs.replaceChildren(...COLS.map(([id, t]) => h("button", { class: "btn sm " + (st.col === id ? "primary" : ""), onclick: () => { st.col = id; st.page = 1; st.q = ""; search.value = ""; st.run = ""; load(); } }, t)),
      h("span", { class: "sp" }), h("span", { class: "muted small" }, `${d.total.toLocaleString()} image${d.total === 1 ? "" : "s"}`));
    runSel.hidden = st.col !== "run";
    if (st.col === "run") runSel.replaceChildren(...d.runs.map(r => h("option", { value: r, selected: r === d.run }, r)));
    note.textContent = NOTE[st.col];
    grid.replaceChildren(...(d.items.length ? d.items.map((it, i) => h("div", { class: "thumb", onclick: () => viewer(i) },
      boxImage(`/api/image?key=${encodeURIComponent(it.key)}&w=360`, boxes(it), it.width ? [it.width, it.height] : null),
      h("div", { class: "meta" }, h("div", { class: "mono", style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, title: it.name }, it.name), h("div", { class: "row", style: { marginTop: "3px" } }, cap(it))))) :
      [empty(st.col === "run" ? "No retraining run has prepared data yet." : st.col === "labels" ? "Nothing has been labelled yet." : st.col === "raw" ? "No images have been sent yet." : "No images match.")]));
    pager.replaceChildren(...(d.pages > 1 ? [h("button", { class: "btn sm", disabled: d.page <= 1, onclick: () => { st.page--; load(); } }, "← Previous"), h("span", { class: "muted small" }, `Page ${d.page} of ${d.pages}`),
      h("button", { class: "btn sm", disabled: d.page >= d.pages, onclick: () => { st.page++; load(); } }, "Next →")] : []));
  }
  async function load() {
    const d = await api(`gallery?collection=${st.col}&page=${st.page}&q=${encodeURIComponent(st.q)}&run=${encodeURIComponent(st.run)}`);
    if (!ctx.live()) return; st.data = d; if (st.col === "run") st.run = d.run; render();
  }
  ctx.actions().append(search, runSel);
  root.replaceChildren(tabs, note, grid, pager);
  await load();
}

// ---------------------------------------------------------------- Requests
async function pageRequests(root, ctx) {
  let filter = "all";
  const grid = h("div", { class: "thumbs" }), sel = h("select", { onchange: e => { filter = e.target.value; draw(); } },
    ["all", "pending", "accepted", "accepted_reviewed", "quarantined", "no_plate", "discarded"].map(v => h("option", { value: v }, v === "all" ? "All statuses" : v.replace(/_/g, " "))));
  let items = [];
  const boxes = it => it.detections.map(d => ({ box: d.box, color: BLUE, label: (d.score * 100).toFixed(0) + "%" }));
  const size = it => it.width ? [Number(it.width), Number(it.height)] : null;
  function draw() {
    const rows = items.filter(i => filter === "all" || i.label_status === filter);
    grid.replaceChildren(...(rows.length ? rows.map(it => h("div", { class: "thumb" + (Date.now() - new Date(it.ts) < 180000 ? " new" : ""), onclick: () => it.s3_key && openModal(detail(it)) },
      it.s3_key ? boxImage(`/api/image?key=${encodeURIComponent(it.s3_key)}&w=420`, boxes(it), size(it)) : h("div", { class: "empty", style: { height: "190px" } }, h("span", { class: "spinner" })),
      h("div", { class: "meta" }, h("div", { class: "row" }, pill(it.label_status || "pending"), h("span", { class: "sp" }), h("span", { class: "muted" }, ago(it.ts))),
        h("div", { class: "muted", style: { marginTop: "4px" } }, it.s3_key ? `${it.n_detections} plate${it.n_detections == 1 ? "" : "s"} · top ${pc(+it.top_confidence)} · ${it.model_version}` : "being processed…")))) : [empty("No requests match. Send a picture from the Detect page.")]));
  }
  function detail(it) {
    return h("div", {}, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Request"), pill(it.label_status || "pending"), h("span", { class: "sp" }), h("button", { class: "btn sm", onclick: closeModal }, "Close")),
      h("div", { class: "mt", style: { textAlign: "center" } }, boxImage(`/api/image?key=${encodeURIComponent(it.s3_key)}`, boxes(it), size(it))),
      h("dl", { class: "mt" }, h("dt", {}, "Id"), h("dd", { class: "mono" }, it.image_id), h("dt", {}, "Received"), h("dd", {}, new Date(it.ts).toLocaleString()),
        h("dt", {}, "Model"), h("dd", {}, it.model_version), h("dt", {}, "Brightness"), h("dd", {}, f2(+it.brightness)), h("dt", {}, "Sharpness"), h("dd", {}, f2(+it.blur_score)), h("dt", {}, "Stored at"), h("dd", { class: "mono" }, it.s3_key)));
  }
  ctx.actions().append(sel);
  const load = async () => { items = (await api("requests?limit=120")).items; if (!ctx.live()) return; live.textContent = `${items.length} request${items.length === 1 ? "" : "s"} · updates every 5 s`; draw(); };
  const live = h("span", { class: "muted small" });
  ctx.actions().prepend(live);
  await load(); ctx.every(load, 5000);
  root.replaceChildren(grid);
}

// ---------------------------------------------------------------- Review
async function pageReview(root) {
  const list = h("div", { class: "grid g2" });
  const legend = h("div", { class: "legend" }, h("span", {}, h("i", { style: { background: BLUE } }), "detector"), h("span", {}, h("i", { style: { background: ORANGE } }), "Nova (second opinion)"));
  const data = (await api("review")).items;
  const card = it => {
    const el = h("div", { class: "card" });
    const act1 = (action, text, cls) => h("button", { class: "btn sm " + (cls || ""), onclick: e => act(e.target, async () => {
      await api("review/" + it.image_id, { json: { action } }); el.remove(); data.splice(data.indexOf(it), 1); if (!data.length) list.replaceChildren(empty("Nothing waiting for review.")); refreshSide();
    }, "Saved") }, text);
    const boxes = [...it.live.map(b => ({ box: b, color: BLUE })), ...it.nova.map(b => ({ box: b, color: ORANGE, dash: true }))];
    el.append(h("div", { style: { textAlign: "center" } }, boxImage(`/api/image?key=${encodeURIComponent(it.s3_key)}`, boxes, [it.width, it.height])),
      h("div", { class: "small muted mt" }, `Detector found ${it.live.length}, Nova found ${it.nova.length}. They disagree, so a person decides.`),
      h("div", { class: "row mt" }, act1("live", "Use detector", ""), act1("nova", "Use Nova", ""), act1("none", "No plate", ""), h("span", { class: "sp" }), act1("discard", "Discard", "danger")));
    return el;
  };
  root.replaceChildren(h("div", { class: "row", style: { marginBottom: "12px" } }, h("div", { class: "muted" }, "Pictures where the two models disagreed. Your choice becomes the training label."), h("span", { class: "sp" }), legend), list);
  list.replaceChildren(...(data.length ? data.map(card) : [empty("Nothing waiting for review.")]));
}

// ---------------------------------------------------------------- Retraining
const STEP_NAMES = { Prepare: "Prepare data", Train: "Fine-tune", Evaluate: "Evaluate", ReleaseRule: "Release rule", "Better?": "Compare", Register: "Register" };
async function pageRetrain(root, ctx) {
  let selected = null, cfg = await api("config");
  const gain = cfg.release.min_map50_gain;
  const startBtn = h("button", { class: "btn primary", onclick: e => act(e.target, async () => {
    if (!confirm("Start a retraining run now?\n\nIt fine-tunes the live model on the collected labels using CPU in the cloud. Expect about 10–60 minutes and roughly $1.")) return CANCELLED;
    const r = await api("retrain/start", { json: {} }); selected = r.run_id || null; await draw(); return r;
  }, r => r.started ? "Run started" : "Not started: " + r.why) }, "Start retraining");
  const stopBtn = h("button", { class: "btn danger", onclick: e => act(e.target, async () => { await api("retrain/stop", { json: { run_id: lastRun } }); await draw(); }, "Run stopped") }, "Stop run");
  let lastRun = null;
  async function draw() {
    const d = await api("retrain" + (selected ? "?run=" + selected : "")), x = d.detail, running = d.lock.status === "running";
    lastRun = d.lock.run_id;
    if (!ctx.live()) return false;
    ctx.actions().replaceChildren(running ? stopBtn : startBtn);
    const steps = x ? h("div", { class: "steps" }, x.stages.map((s, i) => h("div", { class: "step " + s.state },
      h("div", { class: "dot" }, s.state === "done" ? "✓" : s.state === "failed" ? "✕" : i + 1), h("div", { class: "n" }, STEP_NAMES[s.name]),
      h("div", { class: "s" }, { done: "done", running: "in progress", failed: "failed", skipped: "skipped", waiting: "waiting" }[s.state])))) : empty("No run yet. Start one above.");
    const head = x ? h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Run " + x.run_id), pill(x.status), x.outcome ? pill(x.outcome) : null,
      h("span", { class: "sp" }), h("span", { class: "muted small" }, `${x.reason || ""} · ${dur(x.start, x.stop)}`)) : null;
    const m = x?.metrics, ds = x?.dataset;
    const passed = m && m.candidate.ap50 - m.live.ap50 >= gain && m.candidate.recall >= m.live.recall;
    const metrics = m ? h("div", { class: "grid g2 mt" },
      h("div", { class: "card" }, h("h2", {}, "Candidate vs live model (golden set)"), h("div", { class: "chart" }, chartHost("rm")),
        h("div", { class: "small mt", style: { color: passed ? "var(--green)" : "var(--amber)" } }, passed ? `Passes the release rule: AP50 +${f3(m.candidate.ap50 - m.live.ap50)} and recall not lower.` : `Does not pass the release rule (needs AP50 +${gain} and recall not lower; got ${(m.candidate.ap50 - m.live.ap50 >= 0 ? "+" : "") + f3(m.candidate.ap50 - m.live.ap50)}).`)),
      h("div", { class: "card" }, h("h2", {}, "Training data"), ds ? h("dl", {}, h("dt", {}, "Original images"), h("dd", {}, ds.original_images), h("dt", {}, "New labelled images"), h("dd", {}, ds.new_images), h("dt", {}, "Boxes"), h("dd", {}, ds.boxes), h("dt", {}, "Started from"), h("dd", {}, ds.base_version)) : empty("Not prepared yet."),
        h("div", { class: "small muted mt" }, `Golden set: ${m.golden_images} images the model never trains on.`))) : null;
    const lock = h("div", { class: "card mt" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Triggers"), h("span", { class: "sp" }), pill(running ? "running" : "idle")),
      h("div", { class: "grid g3 mt" },
        h("div", {}, h("h3", {}, "New labels"), h("div", {}, `${d.new_labels} of ${d.label_threshold}`), bar(d.new_labels / d.label_threshold)),
        h("div", {}, h("h3", {}, "Minimum gap between automatic runs"), h("div", {}, "24 hours")),
        h("div", {}, h("h3", {}, "Also starts on"), h("div", {}, "weekly schedule, drift alarm, or the button above"))));
    const runs = h("div", { class: "card mt" }, h("h2", {}, "Run history"), h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Run"), h("th", {}, "Status"), h("th", {}, "Started"), h("th", {}, "Duration"))),
      h("tbody", {}, d.runs.map(r => h("tr", { class: "click " + (x && r.run_id === x.run_id ? "sel" : ""), onclick: () => { selected = r.run_id; draw(); } }, h("td", { class: "mono" }, r.run_id), h("td", {}, pill(r.status)), h("td", { class: "muted" }, ago(r.start)), h("td", {}, dur(r.start, r.stop)))))));
    const runBuilds = d.builds.filter(b => !x || b.run_id === x.run_id);
    const logBox = h("div", { class: "logbox", style: { height: "220px" }, id: "buildlog" }, "");
    const builds = h("div", { class: "card mt" }, h("h2", {}, "Cloud jobs for this run"), runBuilds.length ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Stage"), h("th", {}, "Status"), h("th", {}, "Phase"), h("th", {}, "Duration"))),
      h("tbody", {}, runBuilds.map(b => h("tr", {}, h("td", {}, STEP_NAMES[{ prepare: "Prepare", train: "Train", evaluate: "Evaluate" }[b.stage]] || b.stage), h("td", {}, pill(b.status)), h("td", { class: "muted" }, b.phase || ""), h("td", {}, dur(b.start, b.end)))))) : empty("No jobs yet."),
      runBuilds[0]?.log_stream ? h("div", { class: "mt" }, h("h3", {}, "Latest output"), logBox) : null);
    root.replaceChildren(...[h("div", { class: "card" }, head, h("div", { class: "mt" }, steps)), metrics, lock, runs, builds].filter(Boolean));
    if (m) mountChart("rm", ctx, {
      type: "bar", data: { labels: ["AP50", "Recall", "Precision"], datasets: [
        { label: "Live model", data: [m.live.ap50, m.live.recall, m.live.precision], backgroundColor: "#d6d3d1", borderRadius: 4 },
        { label: "Candidate", data: [m.candidate.ap50, m.candidate.recall, m.candidate.precision], backgroundColor: BLUE, borderRadius: 4 }] },
      options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 1 } }, plugins: { legend: { position: "bottom" } }, animation: false } });
    if (runBuilds[0]?.log_stream) {
      const l = await api("build-log?stream=" + encodeURIComponent(runBuilds[0].log_stream) + "&lines=40");
      const box = ctx.live() && $("#buildlog"); if (box) { box.textContent = l.lines.join("\n"); box.scrollTop = box.scrollHeight; }
    }
    return running;
  }
  const holders = {};
  function chartHost(id) { return holders[id] = h("canvas", {}); }
  function mountChart(id, ctx, cfg) { ctx.chart(holders[id], cfg); }
  await draw();
  ctx.every(async () => { await draw(); }, 6000);
}

// ---------------------------------------------------------------- Models
async function pageModels(root, ctx) {
  const draw = async () => {
    const d = await api("models"), ep = d.endpoint, busy = ["Creating", "Updating", "SystemUpdating", "RollingBack"].includes(ep.status);
    const decide = (p, status) => h("button", { class: "btn sm " + (status === "Rejected" ? "danger" : "accent"), onclick: e => act(e.target, async () => {
      if (status === "Approved" && !confirm(`Approve ${p.version}?\n\n${ep.status === "InService" ? "It is deployed to the live endpoint with a blue/green switch and automatic rollback if errors or slowness appear." : "The endpoint is off, so it becomes the version used at the next start."}`)) return CANCELLED;
      await api("models/approval", { json: { arn: p.arn, status } }); draw();
    }, status === "Approved" ? "Approved. Deployment is starting" : "Rejected") }, status === "Approved" ? "Approve & deploy" : "Reject");
    const current = h("div", { class: "card" }, h("div", { class: "row" }, h("h2", { style: { margin: 0 } }, "Live model"), h("b", {}, d.current), h("span", { class: "sp" }), pill(ep.status)),
      busy ? h("div", { class: "mt" }, bar(0, "", true), h("div", { class: "small muted", style: { marginTop: "6px" } }, "Switching to the new model with automatic rollback. The old one keeps serving until the new one is healthy.")) : null,
      h("div", { class: "small muted mt" }, `Baseline v1: AP50 ${f3(d.baseline.ap50_golden)} on the golden set, ${f3(d.baseline.ap50_val)} on the full validation set.`));
    const tbl = d.packages.length ? h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Version"), h("th", {}, "Status"), h("th", {}, "AP50 (golden)"), h("th", {}, "From"), h("th", {}, "Created"), h("th", {}, ""))),
      h("tbody", {}, d.packages.map(p => h("tr", {}, h("td", {}, h("b", {}, p.version), p.version === d.current ? h("span", { class: "muted small" }, " (live)") : null), h("td", {}, pill(p.status)),
        h("td", {}, p.ap50_candidate ? `${f3(+p.ap50_live)} → ${f3(+p.ap50_candidate)}` : "—"), h("td", { class: "muted" }, p.base || ""), h("td", { class: "muted" }, ago(p.created)),
        h("td", { style: { textAlign: "right" } }, p.status === "PendingManualApproval" ? h("div", { class: "row", style: { justifyContent: "flex-end" } }, decide(p, "Approved"), decide(p, "Rejected")) : null))))) : empty("No new model versions yet. A retraining run that beats the live model will appear here for approval.");
    root.replaceChildren(h("div", { class: "grid" }, current, h("div", { class: "card" }, h("h2", {}, "Registered versions"), tbl)));
  };
  await draw(); ctx.every(draw, 6000);
}

// ---------------------------------------------------------------- Monitoring
async function pageMonitoring(root, ctx) {
  let hours = 24;
  const sel = h("select", { onchange: e => { hours = +e.target.value; draw(); } }, [[1, "Last hour"], [6, "Last 6 hours"], [24, "Last 24 hours"], [168, "Last 7 days"]].map(([v, t]) => h("option", { value: v, selected: v === hours }, t)));
  ctx.actions().append(sel);
  const charts = [];
  async function draw() {
    const d = await api("monitoring?hours=" + hours); if (!ctx.live()) return; charts.splice(0).forEach(c => c.destroy());
    const lim = d.limits, S = d.series, fmt = t => { const x = new Date(t); return hours > 24 ? x.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" }) : x.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };
    const labels = k => (S[k] || []).map(p => fmt(p.t)), vals = k => (S[k] || []).map(p => p.v);
    const holder = (title, key, note) => { const c = h("canvas", {}); return [h("div", { class: "card" }, h("h2", {}, title), (S[key] || []).length ? h("div", { class: "chart" }, c) : empty("No data in this range yet."), note ? h("div", { class: "small muted" }, note) : null), c, key]; };
    const defs = [
      holder("Top confidence", "conf", `Alarm below ${lim.min_mean_confidence} when at least ${lim.min_images} images arrive in an hour.`),
      holder("Share of images with no plate", "miss", `Alarm above ${lim.max_no_plate_share * 100}%.`), holder("Images processed", "n"),
      holder("Image brightness", "bright"), holder("Image sharpness", "blur", "Lower means blurrier."), holder("Endpoint calls", "inv"), holder("Model latency (ms)", "lat")];
    const alarmCard = h("div", { class: "card" }, h("h2", {}, "Alarms"), h("div", { class: "grid g4" }, d.alarms.map(a => h("div", { class: "card", style: { padding: "12px 14px" } }, h("div", { class: "row" }, pill(a.state)), h("div", { style: { marginTop: "6px", fontWeight: 600 } }, a.name.replace("plateloop-", "").replace(/-/g, " ")),
      h("div", { class: "small muted" }, a.description || "")))));
    root.replaceChildren(h("div", { class: "grid" }, alarmCard, h("div", { class: "grid g2" }, defs.map(x => x[0]))));
    const line = (canvas, key, color, extra, bars, scale = 1) => {
      const ds = [{ label: key, data: vals(key).map(v => v * scale), borderColor: color, backgroundColor: bars ? color : color + "22", borderWidth: 2, pointRadius: 2, tension: .25, fill: !bars, borderRadius: 3 }];
      if (extra) ds.push({ label: "alarm", data: vals(key).map(() => extra), borderColor: "#dc2626", borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5 });
      charts.push(new Chart(canvas, { type: bars ? "bar" : "line", data: { labels: labels(key), datasets: ds }, options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: !!bars || key === "miss" } } } }));
    };
    for (const [, c, key] of defs) {
      if (!(S[key] || []).length) continue;
      if (key === "conf") line(c, key, BLUE, lim.min_mean_confidence); else if (key === "miss") line(c, key, "#ea580c", lim.max_no_plate_share);
      else if (key === "n" || key === "inv") line(c, key, "#64748b", null, true); else if (key === "lat") line(c, key, "#9333ea", null, false, .001); else line(c, key, "#16a34a");
    }
  }
  ctx.onLeave(() => charts.splice(0).forEach(c => c.destroy()));
  await draw(); ctx.every(draw, 30000);
}

// ---------------------------------------------------------------- Evaluation (measured results)
async function pageEvaluation(root, ctx) {
  const d = await api("evaluation"), e1 = d.e1_results, e2 = d.e2_results, e3 = d.e3_results, ds = d.dataset_stats;
  const gold = e3.brightness.find(x => x.level === "1.0");
  const mk = (title, sub) => { const c = h("canvas", {}); return [h("div", { class: "card" }, h("h2", {}, title), sub ? h("div", { class: "small muted", style: { marginBottom: "8px" } }, sub) : null, h("div", { class: "chart" }, c)), c]; };
  const opts = (extra = {}) => ({ maintainAspectRatio: false, animation: false, plugins: { legend: { position: "bottom" } }, ...extra });
  const sets = [["Full validation", e1.full_val], ["Not in 2k subset", e1.clean_vs_2k_subset], ["Shared with training", e1.leaky_val], ["Held-out sources", e1.clean_holdout], ["Golden set", { AP50: gold.ap50, AP: gold.ap }]];
  const [c1, k1] = mk("Accuracy by evaluation set", "AP50 is the share of plates found with a box that overlaps the true one by at least half.");
  const [c2, k2] = mk("Precision and recall by threshold", "Held-out sources. The chosen threshold is 0.4.");
  const [c3, k3] = mk("Time per image (CPU, 2 threads)", "Milliseconds, median.");
  const drift = (name, title) => { const [c, k] = mk(title, "Accuracy and confidence as the image gets worse."); return [c, k, name]; };
  const dr = [drift("brightness", "Darker images"), drift("blur", "Blurrier images"), drift("noise", "Noisier images")];
  const ratio = v => (+v).toFixed(2);
  const head = h("div", { class: "grid g4" }, kpi(ratio(e1.full_val.AP50), "AP50, full validation set"), kpi(ratio(e1.clean_holdout.AP50), "AP50, held-out sources"), kpi(ratio(gold.ap50), "AP50, golden set (150 images)"), kpi(e2.openvino_2threads.total_ms.median.toFixed(1) + " ms", "Per image, end to end on CPU"));
  const dsTbl = h("div", { class: "card" }, h("h2", {}, "Dataset"), h("table", {}, h("thead", {}, h("tr", {}, ["Set", "Images", "Boxes", "Boxes / image", "Median plate size"].map(t => h("th", {}, t)))),
    h("tbody", {}, Object.entries(ds).map(([k, v]) => h("tr", {}, h("td", {}, k.replace("_", " ")), h("td", {}, v.images.toLocaleString()), h("td", {}, v.boxes.toLocaleString()), h("td", {}, v.boxes_per_image.toFixed(2)), h("td", {}, (v.median_rel_area * 100).toFixed(2) + "% of image"))))));
  root.replaceChildren(h("div", { class: "grid" }, h("div", { class: "muted" }, "Measured on the packaged model v1 with the evaluation scripts in report/experiments."), head,
    h("div", { class: "grid g2" }, c1, c2, c3, ...dr.map(x => x[0])), dsTbl));
  ctx.chart(k1, { type: "bar", data: { labels: sets.map(s => s[0]), datasets: [{ label: "AP50", data: sets.map(s => s[1].AP50), backgroundColor: BLUE, borderRadius: 4 }, { label: "AP50:95", data: sets.map(s => s[1].AP), backgroundColor: "#d6d3d1", borderRadius: 4 }] }, options: opts({ scales: { y: { min: 0, max: 1 } } }) });
  ctx.chart(k2, { type: "line", data: { labels: e1.pr_curve.map(p => p.thr), datasets: [["Precision", "p", BLUE], ["Recall", "r", "#ea580c"], ["F1", "f1", "#16a34a"]].map(([l, k, c]) => ({ label: l, data: e1.pr_curve.map(p => p[k]), borderColor: c, backgroundColor: c, borderWidth: 2, pointRadius: 3, tension: .2 })) }, options: opts({ scales: { y: { min: 0, max: 1 }, x: { title: { display: true, text: "score threshold" } } } }) });
  const o = e2.openvino_2threads;
  ctx.chart(k3, { type: "bar", data: { labels: ["Prepare image", "Model", "Total"], datasets: [{ label: "OpenVINO (served)", data: [o.preprocess_ms.median, o.inference_ms.median, o.total_ms.median], backgroundColor: BLUE, borderRadius: 4 }, { label: "ONNX Runtime", data: [null, e2.onnxruntime_2threads.inference_ms.median, null], backgroundColor: "#d6d3d1", borderRadius: 4 }] }, options: opts() });
  for (const [, k, name] of dr) ctx.chart(k, { type: "line", data: { labels: e3[name].map(x => x.level), datasets: [{ label: "AP50", data: e3[name].map(x => x.ap50), borderColor: BLUE, borderWidth: 2, pointRadius: 3, tension: .2 }, { label: "Mean top confidence", data: e3[name].map(x => x.mean_top_conf), borderColor: "#ea580c", borderWidth: 2, pointRadius: 3, tension: .2 }] }, options: opts({ scales: { y: { min: 0.4, max: 1 } } }) });
}

// ---------------------------------------------------------------- Logs
async function pageLogs(root, ctx) {
  const sources = await api("log-sources"); let source = sources[0], minutes = 60, auto = true, q = "";
  const box = h("div", { class: "logbox" });
  const src = h("select", { onchange: e => { source = e.target.value; draw(); } }, sources.map(s => h("option", { value: s }, s)));
  const mins = h("select", { onchange: e => { minutes = +e.target.value; draw(); } }, [[15, "15 min"], [60, "1 hour"], [360, "6 hours"], [1440, "24 hours"]].map(([v, t]) => h("option", { value: v, selected: v === 60 }, t)));
  const find = h("input", { type: "text", placeholder: "Filter lines", oninput: e => { q = e.target.value.toLowerCase(); render(); } });
  const live = h("label", { class: "row small" }, h("input", { type: "checkbox", checked: true, onchange: e => { auto = e.target.checked; } }), "Live");
  let lines = [];
  function render() {
    const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    box.replaceChildren(...(lines.filter(l => !q || l.m.toLowerCase().includes(q)).map(l => {
      const cls = /error|traceback|exception|failed/i.test(l.m) ? "e" : /warn/i.test(l.m) ? "w" : "";
      return h("div", {}, h("span", { class: "t" }, new Date(l.t).toLocaleTimeString() + "  "), h("span", { class: cls }, l.m));
    })));
    if (!box.childElementCount) box.textContent = "No log lines in this window.";
    if (stick) box.scrollTop = box.scrollHeight;
  }
  async function draw() { lines = (await api(`logs?source=${encodeURIComponent(source)}&minutes=${minutes}`)).lines; render(); }
  ctx.actions().append(src, mins, find, live);
  await draw(); ctx.every(async () => { if (auto) await draw(); }, 5000);
  root.replaceChildren(box);
}

// ---------------------------------------------------------------- start
buildNav(); route(); refreshSide(); setInterval(refreshSide, 15000);
