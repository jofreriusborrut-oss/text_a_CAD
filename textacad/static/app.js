// Text a CAD - interface logic.
// Left: conversation with the assistant. Middle: 3D view and versions.
// Right: parameters, checks, material, simulation, printing and files.
import { Viewer } from "/static/viewer.js";
import { STRINGS } from "/static/strings.js";

const $ = (id) => document.getElementById(id);
const LANGS = ["en", "ca", "es"];

const state = {
  lang: "en",
  config: null,
  session: null,          // payload of the current session
  selected: null,         // version number shown
  material: "petg",
  tab: "params",
  job: null,              // { id, events } while the assistant works
  transient: null,        // error card shown at the end of the conversation
  regenError: null,
  rebuilding: false,
  sims: new Map(),        // key -> { summary, drawing }
  simRunning: false,
  simError: null,
  loadCases: new Map(),   // version stamp -> { load_case, source }
  loadCaseDraft: new Map(), // version stamp -> { mode, simple: {...}, json }
  resolution: "normal",
  useOverride: new Map(), // version stamp -> use case edited by the user
  cache: new Map(),       // materials / print data
  shown: null,            // what the viewer currently shows: "n:stamp"
};

let viewer = null;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function t(key, vars) {
  let text = (STRINGS[state.lang] && STRINGS[state.lang][key]) ?? STRINGS.en[key] ?? key;
  if (vars && typeof text === "string") for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, v);
  return text;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function num(x, decimals = 1) {
  if (x === null || x === undefined || !isFinite(x)) return "–";
  const text = Number(x).toFixed(decimals);
  return state.lang === "en" ? text : text.replace(".", ",");
}

// Up to `decimals` decimals, without trailing zeros: 6.60 -> 6.6, 30.00 -> 30
function trim(x, decimals = 2) {
  if (x === null || x === undefined || !isFinite(x)) return "–";
  const text = String(parseFloat(Number(x).toFixed(decimals)));
  return state.lang === "en" ? text : text.replace(".", ",");
}

function sig(x, digits = 3) {
  if (x === null || x === undefined || !isFinite(x)) return "–";
  const text = String(parseFloat(Number(x).toPrecision(digits)));
  return state.lang === "en" ? text : text.replace(".", ",");
}

async function api(path, { method = "GET", body } = {}) {
  let response;
  const sep = path.includes("?") ? "&" : "?";
  try {
    response = await fetch(`${path}${method === "GET" ? `${sep}lang=${state.lang}` : ""}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify({ lang: state.lang, ...body }) : undefined,
    });
  } catch (err) {
    throw new Error(t("networkError"));
  }
  let data = null;
  try { data = await response.json(); } catch (err) { /* not JSON */ }
  if (!response.ok) throw new Error((data && data.error) || `HTTP ${response.status}`);
  return data;
}

function store(key, value) { try { localStorage.setItem(key, value); } catch (err) { /* private mode */ } }
function recall(key) { try { return localStorage.getItem(key); } catch (err) { return null; } }

function bytesFromBase64(text) {
  const bin = atob(text);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function versions() { return state.session ? state.session.versions : []; }
function version(n = state.selected) { return versions().find((v) => v.number === n) || null; }
function latest() { const v = versions(); return v.length ? v[v.length - 1] : null; }
function fileUrl(v, name, download = false) {
  return `/api/sessions/${state.session.id}/versions/${v.number}/files/${name}?s=${v.stamp}${download ? "&download=1" : ""}`;
}
function simKey(v) { return `${v.number}:${v.stamp}:${state.material}`; }
function materialInfo(id = state.material) { return state.config.materials.find((m) => m.id === id); }
// Name of a material in the language of the interface (results keep the English name).
function materialName(m) { return (materialInfo(m.id) || m).name; }

// ---------------------------------------------------------------------------
// Static texts
// ---------------------------------------------------------------------------

function applyStaticTexts() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $("lang").value = state.lang;
  $("btnSend").textContent = state.job ? t("sending") : t("send");
  $("composerHint").textContent = t("hintEnter");
  $("prompt").placeholder = versions().length ? t("placeholderChange") : t("placeholderNew");
  $("empty").innerHTML = `<div class="inner"><b>${esc(t("emptyTitle"))}</b>${esc(t("emptyText"))}</div>`;
  if (state.config) $("backend").textContent = `${state.config.backend === "cli" ? "claude -p" : "API"} · ${state.config.model}`;
}

// ---------------------------------------------------------------------------
// Conversation
// ---------------------------------------------------------------------------

function listBlock(label, items, cls = "") {
  if (!items || !items.length) return "";
  return `<div class="label">${esc(label)}</div><ul class="${cls}">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
}

function checkPills(v) {
  const count = { ok: 0, warning: 0, error: 0 };
  for (const c of v.checks) if (c.level in count) count[c.level] += 1;
  const pills = [];
  if (count.error) pills.push(`<span class="pill error">${esc(t("checksErr", { n: count.error }))}</span>`);
  if (count.warning) pills.push(`<span class="pill warning">${esc(t("checksWarn", { n: count.warning }))}</span>`);
  if (count.ok) pills.push(`<span class="pill ok">${esc(t("checksOk", { n: count.ok }))}</span>`);
  return pills.join("");
}

function designCard(v) {
  const note = v.note || {};
  const failed = v.attempts.filter((a) => a.error);
  const size = v.info.bbox.size.map((x) => trim(x, 1)).join(" × ");
  const comps = v.components.map((c) => `<span class="chip" title="${esc(c.id)}">${esc(c.name)}</span>`).join(" ");
  const questions = (note.questions || []).map((q) =>
    `<li>${esc(q)} <button class="link" data-answer="${esc(q)}">${esc(t("answerQuestion"))}</button></li>`).join("");
  return `
  <div class="msg card${v.number === state.selected ? " selected" : ""}" data-version="${v.number}">
    <h4><button class="badge" data-select="${v.number}" title="${esc(t("view"))}">v${v.number}</button> ${esc(note.title || "")}
      <span class="muted small">${esc(size)} mm</span></h4>
    <p>${esc(note.summary || "")}</p>
    ${listBlock(t("whatChanged"), note.changes)}
    ${listBlock(t("assumptions"), note.assumptions)}
    ${questions ? `<div class="label">${esc(t("questions"))}</div><ul>${questions}</ul>` : ""}
    ${comps ? `<div class="label">${esc(t("usedData"))}</div><div class="chips">${comps}</div>` : ""}
    <div class="status">${checkPills(v)}
      ${failed.length ? `<span class="pill info">${esc(t("selfFixed", { n: failed.length }))}</span>` : ""}</div>
    ${failed.length ? `<details><summary>${esc(t("showProblems"))}</summary>${failed.map((a) =>
      `<div class="small muted">${esc(t("attempt", { n: a.number, of: v.attempts.length }))}</div><pre>${esc(a.error)}</pre>`).join("")}</details>` : ""}
  </div>`;
}

function messageHtml(m) {
  if (m.role === "user") return `<div class="msg user">${esc(m.text)}</div>`;
  if (m.kind === "design") {
    const v = version(m.version);
    return v ? designCard(v) : "";
  }
  if (m.kind === "questions") {
    const note = m.note || {};
    return `<div class="msg card asking"><h4>${esc(t("needInfo"))}</h4><p>${esc(note.summary || "")}</p>
      <ul>${(note.questions || []).map((q) => `<li>${esc(q)}</li>`).join("")}</ul></div>`;
  }
  if (m.kind === "failed") {
    return `<div class="msg card error"><h4>${esc(t("failedTitle"))}</h4>
      <p>${esc(t("failedText", { n: (m.attempts || []).length }))}</p>
      <details><summary>${esc(t("lastError"))}</summary><pre>${esc(m.error || "")}</pre></details>
      ${m.code ? `<details><summary>${esc(t("lastCode"))}</summary><pre>${esc(m.code)}</pre></details>` : ""}</div>`;
  }
  if (m.kind === "error") {
    return `<div class="msg card error"><h4>${esc(t("claudeError"))}</h4><p>${esc(t("claudeErrorHelp"))}</p>
      <details><summary>${esc(t("lastError"))}</summary><pre>${esc(m.error || "")}</pre></details></div>`;
  }
  return "";
}

function progressHtml() {
  const events = state.job.events || [];
  const last = events[events.length - 1];
  const title = last ? t("attempt", { n: last.attempt, of: last.of }) : t("sending");
  const lines = events.map((e, i) => {
    const detail = e.stage === "error" && e.detail ? `: ${esc(e.detail)}` : "";
    return `<li class="${i === events.length - 1 ? "now" : ""}">${esc(t("stage_" + e.stage))}${detail}</li>`;
  }).join("");
  return `<div class="msg card asking"><div class="progress"><span class="spinner"></span>
    <div><b>${esc(title)}</b><ol>${lines || `<li class="now">${esc(t("stage_asking"))}</li>`}</ol></div></div></div>`;
}

function welcomeHtml() {
  const examples = t("examples").map((e) => `<button type="button" class="example" data-example="${esc(e)}">${esc(e)}</button>`).join("");
  return `<div class="welcome"><h3>${esc(t("welcomeTitle"))}</h3><p>${esc(t("welcomeText"))}</p>${examples}</div>`;
}

function renderMessages() {
  const box = $("messages");
  const msgs = state.session ? state.session.messages : [];
  let html = msgs.length || state.job ? msgs.map(messageHtml).join("") : welcomeHtml();
  if (state.job) html += progressHtml();
  if (state.transient) html += `<div class="msg card error"><p>${esc(state.transient)}</p></div>`;
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
}

function renderComposer() {
  const busy = !!state.job;
  $("btnSend").disabled = busy;
  $("btnSend").textContent = busy ? t("sending") : t("send");
  $("prompt").placeholder = versions().length ? t("placeholderChange") : t("placeholderNew");
  const last = latest();
  const note = $("baseNote");
  if (last && state.selected && state.selected !== last.number) {
    note.hidden = false;
    note.innerHTML = `${esc(t("continuingFrom", { v: "v" + state.selected }))} <button type="button" class="link" id="toLatest">${esc(t("backToLatest"))}</button>`;
    $("toLatest").onclick = () => selectVersion(last.number);
  } else {
    note.hidden = true;
  }
}

let detectTimer = null;
function scheduleDetect() {
  clearTimeout(detectTimer);
  detectTimer = setTimeout(async () => {
    const text = $("prompt").value.trim();
    const box = $("detected");
    if (text.length < 4) { box.hidden = true; return; }
    try {
      const data = await api("/api/detect", { method: "POST", body: { text } });
      if (!data.components.length) { box.hidden = true; return; }
      box.hidden = false;
      box.innerHTML = `<span>${esc(t("usingData"))}</span>` +
        data.components.map((c) => `<span class="chip">${esc(c.name)}</span>`).join("");
    } catch (err) { box.hidden = true; }
  }, 450);
}

async function ensureSession() {
  if (!state.session) {
    state.session = await api("/api/sessions", { method: "POST", body: {} });
    store("textacad.session", state.session.id);
  }
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.job) return;
  state.transient = null;
  try {
    await ensureSession();
    const body = { text };
    const last = latest();
    if (last && state.selected && state.selected !== last.number) body.base = state.selected;
    const data = await api(`/api/sessions/${state.session.id}/messages`, { method: "POST", body });
    state.session.messages.push({ role: "user", text });
    state.job = { id: data.job, events: [] };
    $("prompt").value = "";
    $("detected").hidden = true;
    renderMessages(); renderComposer();
    pollJob();
  } catch (err) {
    state.transient = err.message;
    renderMessages();
  }
}

async function pollJob() {
  if (!state.job) return;
  try {
    const job = await api(`/api/jobs/${state.job.id}`);
    state.job.events = job.events;
    if (job.status === "running") {
      renderMessages();
      setTimeout(pollJob, 700);
      return;
    }
    state.job = null;
    await reloadSession(true);
  } catch (err) {
    state.job = null;
    state.transient = err.message;
    renderAll();
  }
}

async function reloadSession(selectCurrent = false) {
  state.session = await api(`/api/sessions/${state.session.id}`);
  if (selectCurrent || !version(state.selected)) state.selected = state.session.current;
  renderAll();
}

// ---------------------------------------------------------------------------
// Versions and the 3D view
// ---------------------------------------------------------------------------

function renderVersions() {
  const box = $("versions");
  const list = versions();
  box.hidden = list.length === 0;
  box.innerHTML = `<span class="vlabel">${esc(t("versions"))}</span>` + list.map((v) =>
    `<button class="vchip${v.number === state.selected ? " sel" : ""}" data-select="${v.number}" title="${esc(v.instruction)}">
       <b>v${v.number}${v.parent && v.parent !== v.number - 1 ? ` ← v${v.parent}` : ""}</b><span>${esc(v.instruction)}</span></button>`).join("");
  const sel = box.querySelector(".sel");
  if (sel) sel.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function selectVersion(n) {
  if (!version(n)) return;
  state.selected = n;
  state.regenError = null;
  state.simError = null;
  renderAll();
  api(`/api/sessions/${state.session.id}/current`, { method: "POST", body: { version: n } }).catch(() => {});
}

async function renderViewer() {
  const v = version();
  $("empty").hidden = !!v;
  $("dims").hidden = !v;
  $("viewToggles").hidden = !v;
  $("materialBar").hidden = !v;
  if (!v) { viewer.clear(); state.shown = null; $("legend").hidden = true; return; }

  const key = `${v.number}:${v.stamp}`;
  $("dims").textContent = v.info.bbox.size.map((x) => trim(x, 2)).join(" × ") + " mm";
  const hasRef = v.files.includes("reference.stl");
  const parent = v.parent ? version(v.parent) : null;
  $("tglGhostWrap").hidden = !hasRef;
  $("tglCompareWrap").hidden = !parent;
  if (!parent) $("tglCompare").checked = false;

  try {
    if (state.shown !== key) {
      await viewer.loadPart(fileUrl(v, "part.stl"));
      state.shown = key;
      state.stressShown = null;
      await viewer.setGhost(hasRef ? fileUrl(v, "reference.stl") : null);
      viewer.setGhostVisible($("tglGhost").checked);
    }
    await viewer.setCompare($("tglCompare").checked && parent ? fileUrl(parent, "part.stl") : null);
  } catch (err) {
    showViewerMessage(err.message);
  }
  applySimulationToViewer();
}

function applySimulationToViewer() {
  const v = version();
  const sim = v ? state.sims.get(simKey(v)) : null;
  const has = !!(sim && sim.drawing && sim.drawing.points && state.shown === `${v.number}:${v.stamp}`);
  $("tglStressWrap").hidden = !has;
  $("deformWrap").hidden = !has;
  $("legend").hidden = !(has && $("tglStress").checked);
  if (!has) { viewer.clearStress(); state.stressShown = null; return; }
  const d = sim.drawing;
  if (state.stressShown !== sim) {              // build the coloured model only once per result
    const f32 = (text) => new Float32Array(bytesFromBase64(text).buffer);
    viewer.setStress({
      points: f32(d.points), triangles: new Uint32Array(bytesFromBase64(d.triangles).buffer),
      levels: bytesFromBase64(d.stress_levels), displacement: f32(d.displacement), maxDisp: d.max_displacement_mm });
    state.stressShown = sim;
  }
  viewer.setStressVisible($("tglStress").checked);
  viewer.setDeformation($("deform").value / 100);
  $("legendMax").textContent = sig(d.scale_max_mpa, 3);
}

let viewerMsgTimer = null;
function showViewerMessage(text) {
  const box = $("viewerMsg");
  box.textContent = text;
  box.hidden = !text;
  clearTimeout(viewerMsgTimer);
  if (text) viewerMsgTimer = setTimeout(() => { box.hidden = true; }, 7000);
}

// ---------------------------------------------------------------------------
// Inspector: parameters
// ---------------------------------------------------------------------------

function paramsPanel(v) {
  const rows = Object.entries(v.params).map(([name, spec]) => {
    const isCount = spec.unit === "count";
    const range = spec.max - spec.min;
    const step = isCount ? 1 : (range <= 50 ? 0.1 : 0.5);
    const value = v.values[name] ?? spec.value;
    return `<div class="param">
      <label for="p_${esc(name)}">${esc(spec.label || name)}</label>
      <input type="range" id="p_${esc(name)}" data-param="${esc(name)}" min="${spec.min}" max="${spec.max}" step="${step}" value="${value}">
      <span class="num"><input type="number" data-param-num="${esc(name)}" min="${spec.min}" max="${spec.max}" step="${step}" value="${value}">
        <span class="unit">${isCount ? "" : esc(spec.unit || "")}</span></span>
    </div>`;
  }).join("");
  const changed = Object.entries(v.params).some(([name, spec]) => Number(v.values[name]) !== Number(spec.value));
  return `<p class="muted small">${esc(t("paramsHelp"))}</p>
    ${state.regenError ? `<div class="note warning">${esc(t("regenFailed"))}<details><summary>${esc(t("lastError"))}</summary><pre>${esc(state.regenError)}</pre></details></div>` : ""}
    ${state.rebuilding ? `<div class="note">${esc(t("rebuilding"))}</div>` : ""}
    ${rows}
    <div class="row-actions"><button class="btn small" id="resetParams" ${changed ? "" : "disabled"}>${esc(t("resetParams"))}</button></div>`;
}

let paramTimer = null;
function bindParams(v) {
  const panel = $("panel");
  const values = () => {
    const out = {};
    panel.querySelectorAll("[data-param]").forEach((el) => { out[el.dataset.param] = Number(el.value); });
    return out;
  };
  const submit = () => {
    clearTimeout(paramTimer);
    paramTimer = setTimeout(() => rebuild(v, values()), 250);
  };
  panel.querySelectorAll("[data-param]").forEach((el) => {
    const numEl = panel.querySelector(`[data-param-num="${CSS.escape(el.dataset.param)}"]`);
    el.addEventListener("input", () => { numEl.value = el.value; });
    el.addEventListener("change", submit);
    numEl.addEventListener("change", () => {
      const clamped = Math.min(Math.max(Number(numEl.value), Number(el.min)), Number(el.max));
      numEl.value = clamped; el.value = clamped; submit();
    });
  });
  const reset = $("resetParams");
  if (reset) reset.onclick = () => {
    const original = {};
    for (const [name, spec] of Object.entries(v.params)) original[name] = spec.value;
    rebuild(v, original);
  };
}

async function rebuild(v, values) {
  if (state.rebuilding) return;
  state.rebuilding = true; state.regenError = null;
  showViewerMessage(t("rebuilding"));
  try {
    const data = await api(`/api/sessions/${state.session.id}/versions/${v.number}/params`, { method: "POST", body: { values } });
    if (data.ok) {
      const i = state.session.versions.findIndex((x) => x.number === v.number);
      state.session.versions[i] = data.version;
      showViewerMessage("");
    } else {
      state.regenError = data.error;
      showViewerMessage(t("regenFailed"));
    }
  } catch (err) {
    state.regenError = err.message;
    showViewerMessage(err.message);
  }
  state.rebuilding = false;
  renderMessages(); renderViewer(); renderPanel();
}

// ---------------------------------------------------------------------------
// Inspector: checks
// ---------------------------------------------------------------------------

const ICON = { ok: "✓", info: "i", warning: "!", error: "✕" };

function checksPanel(v) {
  const info = v.info;
  const checks = v.checks.map((c) =>
    `<div class="check ${esc(c.level)}"><span class="ic">${ICON[c.level] || "i"}</span><div><b>${esc(c.title)}</b><span>${esc(c.detail)}</span></div></div>`).join("");
  const holes = info.holes == null ? null
    : (info.holes.length ? info.holes.map((h) => `${h.count} × Ø${trim(h.diameter, 2)} (${String(h.axis).toUpperCase()})`).join(", ") : t("none"));
  const com = info.center_of_mass;
  const rows = [
    [t("size"), info.bbox.size.map((x) => trim(x, 2)).join(" × ") + " mm"],
    [t("volume"), num(info.volume_mm3 / 1000, 2) + " cm³"],
    [t("area"), info.area_mm2 != null ? num(info.area_mm2 / 100, 1) + " cm²" : null],
    [t("centerOfMass"), com ? `(${com.map((x) => trim(x, 2)).join("; ")}) mm` : null],
    [t("holes"), holes],
    [t("faces"), info.n_faces],
  ].filter((r) => r[1] !== null && r[1] !== undefined);
  return `${checks}<h3>${esc(t("measured"))}</h3>
    <table class="kv">${rows.map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val)}</td></tr>`).join("")}</table>`;
}

// ---------------------------------------------------------------------------
// Inspector: material
// ---------------------------------------------------------------------------

function defaultUse(v) {
  const use = (v.note && v.note.use) || {};
  const processes = ["fdm", "sls", "cnc"].includes(use.process) ? [use.process] : ["fdm", "sls", "cnc"];
  return { processes, max_temp_c: use.max_temp_c ?? null, outdoor: !!use.outdoor, fluids: !!use.fluids,
    vibration: !!use.vibration, flexible: !!use.flexible };
}

function currentUse(v) {
  if (!state.useOverride.has(v.stamp)) state.useOverride.set(v.stamp, defaultUse(v));
  return state.useOverride.get(v.stamp);
}

async function materialPanel(v) {
  const use = currentUse(v);
  const sim = state.sims.get(simKey(v));
  const key = `mat:${v.number}:${v.stamp}:${JSON.stringify(use)}:${sim ? sim.summary.max_stress_mpa : ""}:${state.lang}`;
  if (!state.cache.has(key)) {
    state.cache.set(key, await api(`/api/sessions/${state.session.id}/versions/${v.number}/materials`, { method: "POST", body: { use } }));
  }
  const data = state.cache.get(key);
  const box = (name) => `<label><input type="checkbox" data-use="${name}" ${use[name] ? "checked" : ""}> ${esc(t(name))}</label>`;
  const proc = (name) => `<label><input type="checkbox" data-proc="${name}" ${use.processes.includes(name) ? "checked" : ""}> ${esc(t(name))}</label>`;
  const cards = data.materials.map((m, i) => {
    const p = m.properties;
    const current = m.id === state.material;
    const sf = m.safety_factor != null ? ` · ${esc(t("sfShort"))} <b>${num(m.safety_factor, 1)}</b> (${esc(t("needShort"))} ${num(m.required_factor, 0)})` : "";
    const why = [
      m.reasons.length ? `<span class="good">+ ${esc(m.reasons.join(", "))}</span>` : "",
      m.warnings.length ? `<span class="bad">− ${esc(m.warnings.join(", "))}</span>` : "",
    ].filter(Boolean).join("<br>");
    return `<div class="mat${current ? " current" : ""}${m.suitable ? "" : " unsuitable"}">
      <div class="mat-head"><b>${m.suitable ? `<span class="rank">${i + 1}</span> ` : ""}${esc(m.name)}</b>
        ${current ? `<span class="pill ok">${esc(t("inUse"))}</span>` : `<button class="btn small" data-material="${esc(m.id)}">${esc(t("useThis"))}</button>`}</div>
      <div class="props">E ${p.E} MPa · σy ${p.yield_strength} MPa · ρ ${num(p.density, 2)} · ≤ ${p.max_service_temp} °C · ${esc(t("massShort"))} ${num(m.mass_g, 1)} g${sf}</div>
      <p class="why">${why}</p><p class="small muted">${esc(m.note)}</p></div>`;
  }).join("");
  return `<h3>${esc(t("useCase"))}</h3>
    <div class="checks-row">${proc("fdm")}${proc("sls")}${proc("cnc")}</div>
    <div class="form"><label>${esc(t("maxTemp"))}<input type="number" id="useTemp" value="${use.max_temp_c ?? ""}" placeholder="${esc(t("unknown"))}"></label></div>
    <div class="checks-row">${box("outdoor")}${box("fluids")}${box("vibration")}${box("flexible")}</div>
    <p class="small muted">${esc(data.use.stress_mpa ? t("fromSimulation", { s: sig(data.use.stress_mpa, 3) }) : t("runSimFirst"))}</p>
    <h3>${esc(t("ranking"))}</h3>${cards}
    <p class="note">${esc(t("typicalValues"))}</p>`;
}

function bindMaterial(v) {
  const panel = $("panel");
  const use = currentUse(v);
  const update = () => { state.useOverride.set(v.stamp, { ...use }); renderPanel(); };
  panel.querySelectorAll("[data-use]").forEach((el) => el.addEventListener("change", () => { use[el.dataset.use] = el.checked; update(); }));
  panel.querySelectorAll("[data-proc]").forEach((el) => el.addEventListener("change", () => {
    const set = new Set(use.processes);
    if (el.checked) set.add(el.dataset.proc); else set.delete(el.dataset.proc);
    use.processes = set.size ? [...set] : ["fdm"];
    update();
  }));
  const temp = $("useTemp");
  if (temp) temp.addEventListener("change", () => { use.max_temp_c = temp.value === "" ? null : Number(temp.value); update(); });
  panel.querySelectorAll("[data-material]").forEach((el) => el.addEventListener("click", () => setMaterial(el.dataset.material)));
}

async function setMaterial(id) {
  state.material = id;
  if (state.session) store(`textacad.material.${state.session.id}`, id);    // the user's choice for this design
  $("materialSelect").value = id;
  state.simError = null;
  await refreshChecksForMaterial();
  renderPanel();
  applySimulationToViewer();
}

// The weight check of a version is computed for one material: fetch it again if another one is selected.
async function refreshChecksForMaterial() {
  const v = version();
  if (!v || v.material === state.material) return;
  try {
    const fresh = await api(`/api/sessions/${state.session.id}/versions/${v.number}?material=${state.material}`);
    const i = state.session.versions.findIndex((x) => x.number === v.number);
    if (i >= 0) state.session.versions[i] = fresh;
  } catch (err) { /* keep the old checks */ }
}

// Material shown for the selected version: the one the user picked for this design,
// otherwise the one suggested from what the assistant knows about its use.
function syncMaterial() {
  const v = version();
  if (!v || !state.session) return;
  const chosen = recall(`textacad.material.${state.session.id}`);
  const want = materialInfo(chosen) ? chosen : (materialInfo(v.suggested_material) ? v.suggested_material : state.config.default_material);
  if (want !== state.material) {
    state.material = want;
    $("materialSelect").value = want;
  }
  if (v.material !== state.material) refreshChecksForMaterial().then(() => { if (state.tab === "checks") renderPanel(); });
}

function fillMaterialSelect() {
  const groups = { fdm: [], sls: [], cnc: [] };
  for (const m of state.config.materials) groups[m.process].push(m);
  $("materialSelect").innerHTML = Object.entries(groups).map(([proc, list]) =>
    `<optgroup label="${esc(t(proc))}">${list.map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("")}</optgroup>`).join("");
  $("materialSelect").value = state.material;
}

// ---------------------------------------------------------------------------
// Inspector: simulation
// ---------------------------------------------------------------------------

const SIDES = ["-x", "+x", "-y", "+y", "-z", "+z"];

async function loadCaseFor(v) {
  if (!state.loadCases.has(v.stamp)) {
    state.loadCases.set(v.stamp, await api(`/api/sessions/${state.session.id}/versions/${v.number}/loadcase`));
  }
  const base = state.loadCases.get(v.stamp);
  if (!state.loadCaseDraft.has(v.stamp)) {
    const lc = base.load_case;
    const simpleOk = lc.fixed.length === 1 && lc.fixed[0].type === "side" && lc.loads.length === 1
      && lc.loads[0].region.type === "side" && !lc.accel_g.some((x) => x);
    const f = simpleOk ? lc.loads[0].force : [0, 0, -50];
    const axis = [0, 1, 2].reduce((a, b) => (Math.abs(f[b]) > Math.abs(f[a]) ? b : a), 0);
    state.loadCaseDraft.set(v.stamp, {
      mode: simpleOk ? "simple" : "advanced",
      simple: {
        hold: simpleOk ? lc.fixed[0].side : "-z",
        push: simpleOk ? lc.loads[0].region.side : "+z",
        force: Math.abs(f[axis]) || 50,
        direction: (f[axis] < 0 ? "-" : "+") + "xyz"[axis],
      },
      json: JSON.stringify(lc, null, 2),
    });
  }
  return { base, draft: state.loadCaseDraft.get(v.stamp) };
}

function draftToLoadCase(draft) {
  if (draft.mode === "advanced") return JSON.parse(draft.json);
  const s = draft.simple;
  const force = [0, 0, 0];
  force["xyz".indexOf(s.direction[1])] = (s.direction[0] === "-" ? -1 : 1) * Math.abs(Number(s.force) || 0);
  return { description: "", fixed: [{ type: "side", side: s.hold }], loads: [{ region: { type: "side", side: s.push }, force }] };
}

function simResultsHtml(v, sim) {
  const s = sim.summary;
  const need = s.required_safety_factor;
  const sf = s.safety_factor;
  const level = sf < 1 ? "error" : (sf < need ? "warning" : "ok");
  const printed = s.material.process !== "cnc";
  const conv = s.convergence;
  const rows = [
    [t("meshInfo"), `${s.n_elements} ${t("elements")} · ${t("size_el")} ${num(s.pitch_mm, 2)} mm`],
    conv ? [t("convergence"), `${t("deflectionWord")} ${num(conv.displacement_change_percent, 1)} % · ${t("stressWord")} ${num(conv.stress_change_percent, 1)} %`] : null,
    [t("equilibrium"), `${sig(Math.hypot(...s.applied_force_n), 4)} N / ${sig(Math.hypot(...s.reaction_force_n), 4)} N`],
    [t("volumeError"), `${s.volume_error >= 0 ? "+" : ""}${num(s.volume_error * 100, 1)} %`],
    [t("atSupports"), `${sig(s.max_stress_at_supports_mpa, 3)} MPa`],
    s.stiffness_n_per_mm ? [t("stiffness"), `${sig(s.stiffness_n_per_mm, 3)} N/mm`] : null,
  ].filter(Boolean);
  const warnings = (s.warning_texts || []).map((w) => `<div class="note warning">${esc(w)}</div>`).join("");
  const sfText = printed
    ? t("sfDetail", { a: num(s.safety_factor, 1), b: num(s.safety_factor_in_plane, 1), need: num(need, 0) })
    : t("sfDetailMetal", { need: num(need, 0) });
  return `<div class="big">
      <div class="stat"><div class="k">${esc(t("maxStress"))}</div><div class="v">${sig(s.max_stress_mpa, 3)} <small>MPa</small></div>
        <div class="small muted">${esc(t("stressAt"))} (${s.max_stress_at.map((x) => trim(x, 1)).join("; ")})</div></div>
      <div class="stat"><div class="k">${esc(t("maxDisp"))}</div><div class="v">${sig(s.max_displacement_mm, 3)} <small>mm</small></div></div>
      <div class="stat ${level}" style="grid-column: 1 / -1"><div class="k">${esc(t("safetyFactor"))} · ${esc(materialName(s.material))}</div>
        <div class="v">${num(sf, 1)}</div><div class="small">${esc(sfText)}</div></div>
    </div>${warnings}
    <table class="kv">${rows.map(([k, val]) => `<tr><th>${esc(k)}</th><td>${esc(val)}</td></tr>`).join("")}</table>
    <p class="small muted">${esc(t("solvedIn", { s: num(s.seconds, 1) }))}</p>`;
}

async function simPanel(v) {
  const { base, draft } = await loadCaseFor(v);
  const sim = state.sims.get(simKey(v));
  const sideOptions = (value) => SIDES.map((s) => `<option value="${s}" ${s === value ? "selected" : ""}>${s.toUpperCase()}</option>`).join("");
  const s = draft.simple;
  const simple = `<div class="form">
      <label>${esc(t("holdSide"))}<select data-lc="hold">${sideOptions(s.hold)}</select></label>
      <label>${esc(t("pushSide"))}<select data-lc="push">${sideOptions(s.push)}</select></label>
      <label>${esc(t("force"))}<input type="number" data-lc="force" min="0" step="1" value="${s.force}"></label>
      <label>${esc(t("direction"))}<select data-lc="direction">${sideOptions(s.direction)}</select></label></div>`;
  const advanced = `<div class="form"><label class="wide"><textarea id="lcJson" spellcheck="false">${esc(draft.json)}</textarea></label></div>`;
  const desc = base.load_case.description && base.source === "script" ? `<p><b>${esc(base.load_case.description)}</b></p>` : "";
  return `<p class="muted small">${esc(t("simIntro"))}</p>
    <h3>${esc(t("loadCase"))}</h3>${desc}
    <p class="small muted">${esc(base.source === "script" ? t("fromAssistant") : t("fromAuto"))}</p>
    <div class="checks-row">
      <label><input type="radio" name="lcMode" value="simple" ${draft.mode === "simple" ? "checked" : ""}> ${esc(t("simple"))}</label>
      <label><input type="radio" name="lcMode" value="advanced" ${draft.mode === "advanced" ? "checked" : ""}> ${esc(t("advanced"))}</label></div>
    ${draft.mode === "simple" ? simple : advanced}
    <div class="form" style="margin-top:8px"><label>${esc(t("resolution"))}<select id="simRes">
      ${state.config.resolutions.map((r) => `<option value="${r}" ${r === state.resolution ? "selected" : ""}>${esc(t(r))}</option>`).join("")}</select></label>
      <label>&nbsp;<button class="btn primary" id="runSim" ${state.simRunning ? "disabled" : ""}>${esc(state.simRunning ? t("running") : t("runSim"))}</button></label></div>
    ${state.simError ? `<div class="note error"><b>${esc(t("simFailed"))}</b><br>${esc(state.simError)}</div>` : ""}
    ${sim ? simResultsHtml(v, sim) : ""}
    <p class="note">${esc(t("simDisclaimer"))}</p>`;
}

function bindSim(v) {
  const panel = $("panel");
  const draft = state.loadCaseDraft.get(v.stamp);
  if (!draft) return;
  panel.querySelectorAll('[name="lcMode"]').forEach((el) => el.addEventListener("change", () => {
    if (el.value === "advanced" && draft.mode === "simple") draft.json = JSON.stringify(draftToLoadCase(draft), null, 2);
    draft.mode = el.value; renderPanel();
  }));
  panel.querySelectorAll("[data-lc]").forEach((el) => el.addEventListener("change", () => { draft.simple[el.dataset.lc] = el.value; }));
  const json = $("lcJson");
  if (json) json.addEventListener("input", () => { draft.json = json.value; });
  $("simRes").addEventListener("change", (e) => { state.resolution = e.target.value; });
  $("runSim").addEventListener("click", () => runSimulation(v));
}

async function runSimulation(v) {
  const draft = state.loadCaseDraft.get(v.stamp);
  let loadCase;
  try { loadCase = draftToLoadCase(draft); } catch (err) { state.simError = "JSON: " + err.message; renderPanel(); return; }
  state.simRunning = true; state.simError = null; renderPanel();
  try {
    const data = await api(`/api/sessions/${state.session.id}/versions/${v.number}/simulate`, {
      method: "POST", body: { material: state.material, resolution: state.resolution, load_case: loadCase } });
    if (data.ok) {
      state.sims.set(simKey(v), { summary: data.summary, drawing: data.drawing });
      $("tglStress").checked = true;
    } else {
      state.simError = data.error;
    }
  } catch (err) {
    state.simError = err.message;
  }
  state.simRunning = false;
  renderPanel();
  applySimulationToViewer();
}

// ---------------------------------------------------------------------------
// Inspector: printing and files
// ---------------------------------------------------------------------------

async function printPanel(v) {
  const key = `print:${v.number}:${v.stamp}:${state.material}:${state.lang}`;
  if (!state.cache.has(key)) {
    state.cache.set(key, await api(`/api/sessions/${state.session.id}/versions/${v.number}/print?material=${state.material}`));
  }
  const d = state.cache.get(key);
  const b = d.best;
  const notes = d.notes.map((n) => `<div class="note">${esc(n)}</div>`).join("");
  const orient = d.orientations.map((o, i) => `<tr class="${i === 0 ? "best" : ""}"><td>${o.up.toUpperCase()}</td>
    <td>${num(o.support_area_mm2 / 100, 1)}</td><td>${num(o.bed_area_mm2 / 100, 1)}</td><td>${trim(o.height_mm, 1)}</td></tr>`).join("");
  const printers = d.printers.map((p) => `<tr><td>${esc(p.name)}</td><td>${p.volume_mm.join(" × ")}</td>
    <td>${p.fits ? `<span class="pill ok">${esc(t("yes"))}</span>` : `<span class="pill error">${esc(t("no"))}</span>`}</td></tr>`).join("");
  const e = d.estimate;
  const ps = d.material.print_settings || {};
  const settings = ps.nozzle_c ? `<h3>${esc(t("settings", { m: materialName(d.material) }))}</h3><table class="kv">
      <tr><th>${esc(t("nozzle"))}</th><td>${esc(ps.nozzle_c)} °C</td></tr><tr><th>${esc(t("bed"))}</th><td>${esc(ps.bed_c)} °C</td></tr>
      <tr><th>${esc(t("enclosure"))}</th><td>${esc(ps.enclosure ? t("needed") : t("notNeeded"))}</td></tr>
      ${ps.hardened_nozzle ? `<tr><th>${esc(t("hardened"))}</th><td>${esc(t("needed"))}</td></tr>` : ""}</table>` : "";
  const estimate = e ? `<h3>${esc(t("estimate"))}</h3><table class="kv">
      <tr><th>${esc(t("plastic"))}</th><td>${num(e.mass_g, 0)} g (${num(e.printed_volume_cm3, 1)} cm³)</td></tr>
      <tr><th>${esc(t("printTime"))}</th><td>${Math.floor(e.time_minutes / 60)} h ${String(e.time_minutes % 60).padStart(2, "0")} min</td></tr>
      <tr><th>${esc(t("cost"))}</th><td>${num(e.material_cost_eur, 2)} €</td></tr></table>`
    : `<div class="note">${esc(t("notForPrinting"))}</div>`;
  return `<p class="muted small">${esc(t("printIntro"))}</p>
    <h3>${esc(t("bestOrientation"))}</h3>
    <table class="kv"><tr><th>${esc(t("axisUp"))}</th><td><b>${b.up.toUpperCase()}</b></td></tr>
      <tr><th>${esc(t("supportArea"))}</th><td>${num(b.support_area_mm2 / 100, 1)} cm²</td></tr>
      <tr><th>${esc(t("bedContact"))}</th><td>${num(b.bed_area_mm2 / 100, 1)} cm²</td></tr>
      <tr><th>${esc(t("height"))}</th><td>${trim(b.height_mm, 1)} mm</td></tr></table>
    ${notes}${estimate}${settings}
    <h3>${esc(t("orientations"))}</h3>
    <table class="grid"><tr><th>${esc(t("axisUp"))}</th><th>${esc(t("supportArea"))} cm²</th><th>${esc(t("bedContact"))} cm²</th><th>${esc(t("height"))} mm</th></tr>${orient}</table>
    <h3>${esc(t("fitsPrinters"))}</h3><table class="grid">${printers}</table>`;
}

function filesPanel(v) {
  const item = (name, title, desc) => v.files.includes(name)
    ? `<div class="file"><div><b>${esc(title)}</b><span>${esc(desc)}</span></div>
        <a class="btn small" href="${fileUrl(v, name, true)}" download>${esc(t("download"))}</a></div>` : "";
  return `<p class="muted small">${esc(t("filesIntro"))}</p>
    ${item("part.step", "STEP", t("stepDesc"))}${item("part.stl", "STL", t("stlDesc"))}${item("part.3mf", "3MF", t("mfDesc"))}
    ${item("reference.stl", "STL · " + t("showReference"), t("refDesc"))}
    <div class="file"><div><b>Python</b><span>${esc(t("codeDesc"))}</span></div>
      <a class="btn small" href="${fileUrl(v, "code.py", true)}" download>${esc(t("download"))}</a></div>
    <div class="file"><div><b>HTML</b><span>${esc(t("reportDesc"))}</span></div>
      <button class="btn small" id="makeReport">${esc(t("openReport"))}</button></div>
    <h3>${esc(t("script"))} <button class="link" id="copyCode">${esc(t("copy"))}</button></h3>
    <pre id="codeBox" style="max-height:420px">${esc(v.code)}</pre>`;
}

function bindFiles(v) {
  $("copyCode").onclick = async () => {
    try { await navigator.clipboard.writeText(v.code); $("copyCode").textContent = t("copied"); } catch (err) { /* select manually */ }
  };
  $("makeReport").onclick = async () => {
    try {
      const data = await api(`/api/sessions/${state.session.id}/versions/${v.number}/report`, {
        method: "POST", body: { material: state.material, image: viewer.screenshot() } });
      const url = URL.createObjectURL(new Blob([data.html], { type: "text/html" }));
      const link = document.createElement("a");
      link.href = url; link.download = data.name; link.click();
      window.open(url, "_blank");
    } catch (err) { showViewerMessage(err.message); }
  };
}

// ---------------------------------------------------------------------------
// Inspector frame
// ---------------------------------------------------------------------------

let panelToken = 0;
async function renderPanel() {
  const panel = $("panel");
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === state.tab)));
  const v = version();
  if (!v) { panel.innerHTML = `<div class="none">${esc(t("noPart"))}</div>`; return; }
  const token = ++panelToken;
  const scroll = panel.scrollTop;
  try {
    let html = "";
    if (state.tab === "params") html = paramsPanel(v);
    else if (state.tab === "checks") html = checksPanel(v);
    else if (state.tab === "material") html = await materialPanel(v);
    else if (state.tab === "sim") html = await simPanel(v);
    else if (state.tab === "print") html = await printPanel(v);
    else html = filesPanel(v);
    if (token !== panelToken) return;           // a newer render started meanwhile
    panel.innerHTML = html;
    panel.scrollTop = scroll;
    if (state.tab === "params") bindParams(v);
    else if (state.tab === "material") bindMaterial(v);
    else if (state.tab === "sim") bindSim(v);
    else if (state.tab === "files") bindFiles(v);
  } catch (err) {
    if (token === panelToken) panel.innerHTML = `<div class="note error">${esc(err.message)}</div>`;
  }
}

function renderAll() {
  $("sessionTitle").textContent = state.session && state.session.title ? state.session.title : "";
  syncMaterial();
  renderMessages(); renderComposer(); renderVersions(); renderViewer(); renderPanel();
}

// ---------------------------------------------------------------------------
// Dialogs: saved designs and the component catalogue
// ---------------------------------------------------------------------------

function openDialog(html) {
  $("dialogBody").innerHTML = html;
  const dialog = $("dialog");
  if (!dialog.open) dialog.showModal();
  $("dialogBody").querySelectorAll("[data-close]").forEach((b) => { b.onclick = () => dialog.close(); });
}

async function sessionsDialog() {
  const data = await api("/api/sessions");
  const items = data.sessions.map((s) => `<div class="list-item"><div class="t"><b>${esc(s.title)}</b>
      <span class="small muted">${new Date(s.created * 1000).toLocaleString(state.lang)} · ${esc(t("versionsCount", { n: s.versions }))}</span></div>
      <div><button class="btn small" data-open="${esc(s.id)}">${esc(t("open"))}</button>
      <button class="btn small danger" data-delete="${esc(s.id)}">${esc(t("remove"))}</button></div></div>`).join("");
  openDialog(`<h2>${esc(t("sessionsTitle"))} <button class="btn small" data-close>${esc(t("close"))}</button></h2>
    ${items || `<p class="muted">${esc(t("noSessions"))}</p>`}`);
  $("dialogBody").querySelectorAll("[data-open]").forEach((b) => { b.onclick = async () => { $("dialog").close(); await openSession(b.dataset.open); }; });
  $("dialogBody").querySelectorAll("[data-delete]").forEach((b) => {
    b.onclick = async () => {
      if (b.dataset.armed !== "1") { b.dataset.armed = "1"; b.textContent = t("confirmDelete"); return; }
      await api(`/api/sessions/${b.dataset.delete}`, { method: "DELETE" });
      if (state.session && state.session.id === b.dataset.delete) newDesign();
      sessionsDialog();
    };
  });
}

async function openSession(id) {
  resetSessionState();
  state.session = await api(`/api/sessions/${id}`);
  state.selected = state.session.current;
  store("textacad.session", id);
  renderAll();
}

function resetSessionState() {
  state.sims.clear(); state.loadCases.clear(); state.loadCaseDraft.clear(); state.useOverride.clear(); state.cache.clear();
  state.regenError = null; state.simError = null; state.transient = null; state.shown = null; state.job = null;
}

function newDesign() {
  resetSessionState();
  state.session = null; state.selected = null;
  store("textacad.session", "");
  renderAll();
  $("prompt").focus();
}

async function catalogDialog(query = "") {
  const data = await api(`/api/catalog?q=${encodeURIComponent(query)}`);
  const items = data.components.map((c) => {
    const dims = Object.entries(c.dims || {}).map(([k, v]) => `${k} = ${v}`).join(" · ");
    const mine = c.id.startsWith("user-");
    return `<div class="comp"><div class="list-item" style="border:0;padding:0"><div class="t"><b>${esc(c.name)}</b></div>
        <div><span class="pill ${c.confidence === "typical" ? "warning" : "info"}">${esc(t("data_" + c.confidence))}</span>
        ${mine ? `<button class="btn small danger" data-remove="${esc(c.id)}">${esc(t("remove"))}</button>` : ""}</div></div>
      <div class="dims-text">${esc(dims)}</div>${c.notes ? `<div class="small muted">${esc(c.notes)}</div>` : ""}</div>`;
  }).join("");
  openDialog(`<h2>${esc(t("catalogTitle"))} <button class="btn small" data-close>${esc(t("close"))}</button></h2>
    <p class="muted small">${esc(t("catalogIntro"))}</p>
    <input class="search" id="catSearch" value="${esc(query)}" placeholder="${esc(t("search"))}">
    <details><summary>${esc(t("addComponent"))}</summary>
      <div class="form" style="margin-top:8px">
        <label class="wide">${esc(t("compName"))}<input id="compName"></label>
        <label class="wide">${esc(t("compKeywords"))}<input id="compKeywords"></label>
        <label class="wide">${esc(t("compDims"))}<textarea id="compDims" placeholder="body_diameter = 12.7&#10;stroke = 100"></textarea></label>
        <label class="wide">${esc(t("compNotes"))}<input id="compNotes"></label>
        <label><button class="btn primary" id="compSave">${esc(t("save"))}</button></label><label id="compError" class="small" style="color:var(--err)"></label>
      </div></details>
    <div id="catList">${items}</div>`);
  const search = $("catSearch");
  let timer = null;
  search.oninput = () => { clearTimeout(timer); timer = setTimeout(() => catalogDialog(search.value), 300); };
  if (query) { search.focus(); search.setSelectionRange(query.length, query.length); }
  $("dialogBody").querySelectorAll("[data-remove]").forEach((b) => {
    b.onclick = async () => { await api(`/api/catalog/${b.dataset.remove}`, { method: "DELETE" }); catalogDialog(search.value); };
  });
  $("compSave").onclick = async () => {
    const dims = {};
    for (const line of $("compDims").value.split("\n")) {
      const [k, ...rest] = line.split("=");
      if (!rest.length || !k.trim()) continue;
      const raw = rest.join("=").trim().replace(",", ".");
      dims[k.trim()] = raw !== "" && !isNaN(Number(raw)) ? Number(raw) : rest.join("=").trim();
    }
    try {
      await api("/api/catalog", { method: "POST", body: {
        name: $("compName").value, dims, notes: $("compNotes").value,
        keywords: $("compKeywords").value.split(",").map((s) => s.trim()).filter(Boolean) } });
      catalogDialog($("compName").value);
    } catch (err) { $("compError").textContent = err.message; }
  };
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function changeLanguage(lang) {
  state.lang = LANGS.includes(lang) ? lang : "en";
  store("textacad.lang", state.lang);
  state.cache.clear();
  state.config = await api("/api/config");
  fillMaterialSelect();
  applyStaticTexts();
  if (state.session && state.session.id && versions().length) {
    // Check texts come from the server in the chosen language; simulation warnings too.
    state.sims.clear();
    await reloadSession();
  } else {
    renderAll();
  }
}

function bindGlobal() {
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); sendMessage($("prompt").value); });
  $("prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage($("prompt").value); }
  });
  $("prompt").addEventListener("input", scheduleDetect);
  $("messages").addEventListener("click", (e) => {
    const sel = e.target.closest("[data-select]");
    if (sel) { selectVersion(Number(sel.dataset.select)); return; }
    const example = e.target.closest("[data-example]");
    if (example) { $("prompt").value = example.dataset.example; $("prompt").focus(); scheduleDetect(); return; }
    const answer = e.target.closest("[data-answer]");
    if (answer) { $("prompt").value = answer.dataset.answer + " "; $("prompt").focus(); }
  });
  $("versions").addEventListener("click", (e) => {
    const sel = e.target.closest("[data-select]");
    if (sel) selectVersion(Number(sel.dataset.select));
  });
  $("tabs").addEventListener("click", (e) => {
    const tab = e.target.closest("[data-tab]");
    if (tab) { state.tab = tab.dataset.tab; renderPanel(); }
  });
  $("viewButtons").addEventListener("click", (e) => { if (e.target.dataset.v) viewer.setView(e.target.dataset.v); });
  $("tglGhost").addEventListener("change", (e) => viewer.setGhostVisible(e.target.checked));
  $("tglCompare").addEventListener("change", () => renderViewer());
  $("tglStress").addEventListener("change", () => applySimulationToViewer());
  $("deform").addEventListener("input", (e) => viewer.setDeformation(e.target.value / 100));
  $("materialSelect").addEventListener("change", (e) => setMaterial(e.target.value));
  $("lang").addEventListener("change", (e) => changeLanguage(e.target.value));
  $("btnNew").addEventListener("click", newDesign);
  $("btnOpen").addEventListener("click", () => sessionsDialog().catch((err) => showViewerMessage(err.message)));
  $("btnCatalog").addEventListener("click", () => catalogDialog().catch((err) => showViewerMessage(err.message)));
  $("dialog").addEventListener("click", (e) => { if (e.target === $("dialog")) $("dialog").close(); });
}

async function start() {
  const saved = recall("textacad.lang");
  const browser = (navigator.language || "en").slice(0, 2).toLowerCase();
  state.lang = LANGS.includes(saved) ? saved : (LANGS.includes(browser) ? browser : "en");
  viewer = new Viewer($("viewer"));
  bindGlobal();
  try {
    state.config = await api("/api/config");
  } catch (err) {
    $("messages").innerHTML = `<div class="msg card error"><p>${esc(err.message)}</p></div>`;
    return;
  }
  state.material = state.config.default_material;
  fillMaterialSelect();
  applyStaticTexts();
  const last = recall("textacad.session");
  if (last) {
    try {
      state.session = await api(`/api/sessions/${last}`);
      state.selected = state.session.current;
    } catch (err) { state.session = null; }
  }
  renderAll();
  if (state.session && state.session.busy) {       // the page was reloaded while the assistant was working
    setTimeout(() => reloadSession(true).catch(() => {}), 2500);
  }
}

start();
