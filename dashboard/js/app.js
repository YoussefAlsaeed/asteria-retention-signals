import { cssVar, dataTable, h, lineChart, scatterChart } from "./charts.js";

// Colour follows the entity (country), never its rank, so filtering never repaints a country.
const COUNTRY_SLOT = { GR: "--s1", RO: "--s2", PL: "--s3", IT: "--s4", IE: "--s5", BG: "--s6" };
const STATUS = {
  met: { icon: "✓", label: "Met" },
  not_met: { icon: "✕", label: "Not met" },
  pending: { icon: "…", label: "Pending" },
  insufficient_sample: { icon: "?", label: "Too few people" },
};
const CONFIDENCE = { clear: "Clear: the 95% interval is entirely on one side of the target",
  within_uncertainty: "Too close to call: the 95% interval includes the target" };
const SEVERITY = { corrected: "Corrected", warn: "Kept, flagged", exclude: "Excluded from all measures",
  exclude_country: "Excluded from country views", error: "Fails the run" };

const $ = (id) => document.getElementById(id);
const pct = (v, d = 1) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(d)}%`);
const num = (v, d = 0) => (v === null || v === undefined ? "–"
  : Number(v).toLocaleString("en-GB", { maximumFractionDigits: d, minimumFractionDigits: d }));
const asDate = (s) => new Date(`${s}T00:00:00Z`);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let meta = null;
let trust = null;
let cache = null;
const state = {};

class ApiError extends Error {
  constructor(kind, message) { super(message); this.kind = kind; }
}

async function api(path) {
  let response;
  try {
    response = await fetch(`/api/${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("network", "Cannot reach the API. Is `uv run asteria serve` running?");
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep the status text */ }
    throw new ApiError(response.status === 503 ? "not_ready" : "http", detail);
  }
  return response.json();
}

function periodLabel(start, grain, objective) {
  const d = asDate(start);
  const y = d.getUTCFullYear();
  if (objective && objective.measure === "trailing_regretted_turnover") {
    const end = grain === "year" ? new Date(Date.UTC(y, 11, 1))
      : grain === "quarter" ? new Date(Date.UTC(y, d.getUTCMonth() + 2, 1)) : d;
    return `12 months to ${MONTHS[end.getUTCMonth()]} ${end.getUTCFullYear()}`;
  }
  if (grain === "year") return `${y} hires`;
  if (grain === "quarter") return `${y} Q${Math.floor(d.getUTCMonth() / 3) + 1} hires`;
  return `${MONTHS[d.getUTCMonth()]} ${y} hires`;
}

const objective = () => meta.objectives.find((o) => o.objective_id === state.objective);
const signal = () => meta.signals.find((s) => s.indicator_id === state.signal);
const countryName = (code) => (code === "ALL" ? "All countries" : meta.countries.find((c) => c.code === code)?.name ?? code);
const targetLabel = (o) => `Target ${o.direction === "at_least" ? "≥" : "≤"} ${pct(o.target)}`;

// ------------------------------------------------------------------ banner
function showBanner(error) {
  const text = error.kind === "not_ready" ? `Data not built yet. ${error.message}` : error.message;
  $("banner-text").textContent = text;
  $("banner").hidden = false;
}
const hideBanner = () => { $("banner").hidden = true; };

// ------------------------------------------------------------------ filters
function option(value, label) { return h("option", { value, text: label }); }

function readUrl() {
  const q = new URLSearchParams(location.search);
  state.objective = q.get("objective") || meta.objectives[0].objective_id;
  state.country = q.get("country") || "ALL";
  state.segment = q.get("segment") || "All";
  state.grain = q.get("grain") || "year";
  state.variant = q.get("variant") || "main";
  state.signal = q.get("signal") || meta.signals[0].indicator_id;
  if (!meta.objectives.some((o) => o.objective_id === state.objective)) state.objective = meta.objectives[0].objective_id;
  if (!objective().variants.includes(state.variant)) state.variant = "main";
}

function writeUrl() {
  history.replaceState(null, "", `?${new URLSearchParams(state)}`);
}

function buildFilters() {
  $("f-objective").replaceChildren(...meta.objectives.map((o) => option(o.objective_id, o.name)));
  $("f-country").replaceChildren(option("ALL", "All countries"), ...meta.countries.map((c) => option(c.code, c.name)));
  $("f-segment").replaceChildren(option("All", "All"), ...meta.segments.map((s) => option(s, s)));
  $("segment-label").textContent = meta.segment_name.replace("_", " ").replace(/^./, (c) => c.toUpperCase());
  $("f-signal").replaceChildren(...meta.signals.map((s) => option(s.indicator_id, s.title.split(",")[0])));
  syncFilters();
  for (const id of ["objective", "country", "segment", "grain", "variant", "signal"]) {
    $(`f-${id}`).addEventListener("change", (e) => {
      state[id] = e.target.value;
      if (id === "objective" && !objective().variants.includes(state.variant)) state.variant = "main";
      syncFilters();
      refresh();
    });
  }
}

function syncFilters() {
  const variantLabels = { main: "Main (assumption)", sensitivity_manager: "Senior + Manager",
    upper_bound_unknown: "Unknown regrets counted" };
  $("f-variant").replaceChildren(...objective().variants.map((v) => option(v, variantLabels[v] || v)));
  for (const id of ["objective", "country", "segment", "grain", "variant", "signal"]) $(`f-${id}`).value = state[id];
  writeUrl();
}

// ------------------------------------------------------------------ data
async function refresh() {
  $("main").setAttribute("aria-busy", "true");  // previous render stays, dimmed
  const o = state.objective, c = state.country, s = state.segment;
  try {
    const [tiles, series, signalSeries, assoc, cells] = await Promise.all([
      api(`status?country=${c}&segment=${encodeURIComponent(s)}&grain=${state.grain}`),
      api(`objectives/${o}/measures?country=${c}&segment=${encodeURIComponent(s)}&grain=${state.grain}&variant=${state.variant}`),
      api(`signals/${state.signal}?country=${c}`),
      api(`objectives/${o}/associations`),
      api(`objectives/${o}/associations/${state.signal}/cells`),
    ]);
    trust = trust || await api("trust");
    cache = { tiles, series, signalSeries, assoc, cells };
    hideBanner();
    drawAll();
  } catch (error) {
    showBanner(error);
  } finally {
    $("main").setAttribute("aria-busy", "false");
  }
}

function drawAll() {
  if (!cache) return;
  drawTiles(cache.tiles);
  drawTrend(cache.series);
  drawSignal(cache.signalSeries);
  drawScatter(cache.cells);
  drawAssociations(cache.assoc);
  drawTrust();
}

// ------------------------------------------------------------------ status tiles
function drawTiles(rows) {
  const scope = `${countryName(state.country)}${state.segment === "All" ? "" : ` · ${state.segment}`}`;
  $("tiles").replaceChildren(...meta.objectives.map((o) => {
    const r = rows.find((x) => x.objective_id === o.objective_id);
    if (!r) {
      return h("article", { class: "tile" }, [h("h3", { text: o.name }),
        h("p", { class: "period", text: scope }),
        h("div", { class: "empty", text: "No measured period for this selection yet." })]);
    }
    const st = STATUS[r.status];
    const unit = o.measure === "cohort_retention" ? `${num(r.denominator)} hires`
      : `average headcount ${num(r.denominator)}`;
    return h("article", { class: `tile ${r.status}`, "aria-label": `${o.name}: ${pct(r.rate)}, ${st.label}` }, [
      h("h3", { text: o.name }),
      h("p", { class: "period", text: `${periodLabel(r.period_start, state.grain, o)} · ${scope}` }),
      h("p", { class: "value", text: pct(r.rate) }),
      h("p", { class: "target", text: targetLabel(o) }),
      h("span", { class: `badge ${r.status}` }, [h("span", { class: "icon", "aria-hidden": "true", text: st.icon }),
        h("span", { text: st.label })]),
      h("p", { class: "detail", text: r.confidence ? CONFIDENCE[r.confidence] : "Interval not assessed: sample too small." }),
      h("p", { class: "detail", text: `95% interval ${pct(r.ci_low)} – ${pct(r.ci_high)} · ${unit}` +
        (r.pending_periods ? ` · ${r.pending_periods} later period(s) pending` : "") }),
    ]);
  }));
}

// ------------------------------------------------------------------ trend
function drawTrend(series) {
  const o = objective();
  $("trend-title").textContent = o.name;
  $("trend-sub").textContent = `${countryName(state.country)} · ${state.segment} · by ${state.grain}` +
    (state.variant === "main" ? "" : ` · definition: ${$("f-variant").selectedOptions[0].textContent}`);
  const chart = $("trend-chart");
  const pts = series.points;
  const measured = pts.filter((p) => p.rate !== null);
  const pending = pts.filter((p) => p.status === "pending").length;
  const small = pts.filter((p) => p.status === "insufficient_sample").length;
  const accent = cssVar("--accent");
  $("trend-legend").replaceChildren(...[
    h("li", {}, [h("span", { class: "key-line", style: `background:${accent}` }), h("span", { text: "Rate" })]),
    h("li", {}, [h("span", { class: "key-band", style: `background:${accent}` }), h("span", { text: "95% interval" })]),
    h("li", {}, [h("span", { class: "key-line", style: `background:${cssVar("--ink-2")}` }), h("span", { text: targetLabel(o) })]),
    small ? h("li", {}, [h("span", { class: "key-hollow" }), h("span", { text: `Fewer than ${meta.min_sample} people` })]) : null,
  ].filter(Boolean));
  if (!pts.length) {
    chart.replaceChildren(h("div", { class: "empty", text: "No hires in this slice. Try a wider period or another business unit." }));
  } else if (!measured.length) {
    chart.replaceChildren(h("div", { class: "empty", text: "Every period in this slice is still pending: its observation window has not finished." }));
  } else {
    lineChart(chart, {
      ariaLabel: `${o.name}, ${countryName(state.country)}, by ${state.grain}. Latest ${pct(measured.at(-1).rate)} against ${targetLabel(o)}. Use arrow keys to read values.`,
      series: [{ id: "rate", label: "Rate", color: accent, points: pts.map((p) => ({
        x: asDate(p.period_start), y: p.rate, lo: p.ci_low, hi: p.ci_high, hollow: p.status === "insufficient_sample",
        extra: `${STATUS[p.status].label}, n ${num(p.denominator)}` })) }],
      target: { value: o.target, label: targetLabel(o) },
      band: true, yFormat: (v) => pct(v, 0), xFormat: (d) => periodLabel(d.toISOString().slice(0, 10), state.grain, o),
    });
  }
  $("trend-note").textContent = [pending ? `${pending} period(s) pending (not yet measurable).` : "",
    small ? `${small} period(s) with fewer than ${meta.min_sample} people: shown hollow, no status judged.` : ""].join(" ").trim();
  $("trend-table").replaceChildren(dataTable([
    { key: "period_start", label: "Period", format: (v) => periodLabel(v, state.grain, o) },
    { key: "numerator", label: o.measure === "cohort_retention" ? "Retained" : "Regretted exits", num: true, format: (v) => num(v) },
    { key: "denominator", label: o.measure === "cohort_retention" ? "Hires" : "Avg headcount", num: true, format: (v) => num(v, 1) },
    { key: "rate", label: "Rate", num: true, format: (v) => pct(v) },
    { key: "ci_low", label: "95% interval", format: (v, r) => (v === null ? "–" : `${pct(v)} – ${pct(r.ci_high)}`) },
    { key: "status", label: "Status", format: (v) => STATUS[v].label },
  ], pts, { caption: `${o.name} data` }));
}

// ------------------------------------------------------------------ signal
function drawSignal(seriesList) {
  const s = signal();
  $("signal-title").textContent = s.title;
  $("signal-sub").textContent = `${s.unit}. Value known at the start of each month (published data only; ${s.lag_days}-day publication lag). Source: ${s.provider}.`;
  const chart = $("signal-chart");
  const series = seriesList.filter((x) => x.points.some((p) => p.value !== null)).map((x) => ({
    id: x.country, label: countryName(x.country), color: cssVar(COUNTRY_SLOT[x.country] || "--s1"),
    points: x.points.map((p) => ({ x: asDate(p.as_of_date), y: p.value,
      extra: p.signal_period_start ? `describes ${describePeriod(p)}, ${p.signal_age_days} days old` : "" })),
  }));
  $("signal-legend").replaceChildren(...(series.length > 1 ? series.map((x) =>
    h("li", {}, [h("span", { class: "key-line", style: `background:${x.color}` }), h("span", { text: x.label })])) : []));
  if (!series.length) {
    chart.replaceChildren(h("div", { class: "empty", text: "No published values for this selection." }));
  } else {
    lineChart(chart, { ariaLabel: `${s.title} for ${countryName(state.country)}, as known each month. Use arrow keys to read values.`,
      series, step: true, yFormat: (v) => num(v, 1), xFormat: (d) => `Known on 1 ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` });
  }
  $("signal-note").textContent = s.frequency === "A"
    ? "Annual figures are carried forward until the next year is published; each value keeps its own year and age."
    : s.frequency === "Q" ? "Quarterly figures are carried forward until the next quarter is published." : "";
  const rows = seriesList.flatMap((x) => x.points.map((p) => ({ ...p, country: countryName(x.country) })));
  $("signal-table").replaceChildren(dataTable([
    { key: "country", label: "Country" },
    { key: "as_of_date", label: "Known on" },
    { key: "value", label: "Value", num: true, format: (v) => num(v, 2) },
    { key: "signal_period_start", label: "Describes", format: (v, r) => (v ? describePeriod(r) : "–") },
    { key: "signal_age_days", label: "Age (days)", num: true },
    { key: "signal_status_label", label: "Provider flag" },
  ], rows, { caption: `${s.title} values` }));
}

function describePeriod(p) {
  const d = asDate(p.signal_period_start);
  if (p.signal_frequency === "A") return String(d.getUTCFullYear());
  if (p.signal_frequency === "Q") return `${d.getUTCFullYear()} Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

// ------------------------------------------------------------------ challenge
function drawScatter(cells) {
  const o = objective(), s = signal();
  const cohort = o.measure === "cohort_retention";
  const yLabel = cohort ? `Share who left within ${o.months} months` : "Regretted exits per person-month";
  $("scatter-title").textContent = `${yLabel} vs ${s.title.split(",")[0].toLowerCase()}`;
  $("scatter-sub").textContent = `One dot per country and quarter (${cohort ? "hire quarter" : "calendar quarter"}); signal as known at the time.`;
  const chart = $("scatter-chart");
  const highlight = state.country !== "ALL";
  $("scatter-legend").replaceChildren(...[
    h("li", {}, [h("span", { class: "key-dot", style: `background:${cssVar("--accent")}` }),
      h("span", { text: highlight ? countryName(state.country) : "Country-quarter" })]),
    highlight ? h("li", {}, [h("span", { class: "key-dot", style: `background:${cssVar("--de-emphasis")}` }), h("span", { text: "Other countries" })]) : null,
    h("li", {}, [h("span", { text: "Larger dot = more people" })]),
  ].filter(Boolean));
  if (!cells.length) {
    chart.replaceChildren(h("div", { class: "empty", text: "No overlapping signal and outcome data for this selection." }));
  } else {
    const who = cohort ? "hires" : "person-months";
    scatterChart(chart, {
      ariaLabel: `${yLabel} against ${s.title}, ${cells.length} country-quarters. Use arrow keys to read points.`,
      xLabel: `${s.title.split(",")[0]} (${s.unit})`, yLabel,
      xFormat: (v) => num(v, 1), yFormat: (v) => pct(v, cohort ? 0 : 1),
      points: cells.map((c) => ({
        x: c.signal_mean, y: c.event_rate, n: c.n, emphasis: !highlight || c.country_code === state.country,
        label: `${countryName(c.country_code)} · ${describePeriod({ signal_frequency: "Q", signal_period_start: c.period_start })}`,
        detail: [{ value: pct(c.event_rate, 1), label: yLabel.toLowerCase() },
          { value: num(c.signal_mean, 2), label: s.unit },
          { value: num(c.n), label: `${who}, ${c.events} left` }],
      })),
    });
  }
  $("scatter-table").replaceChildren(dataTable([
    { key: "country_code", label: "Country", format: countryName },
    { key: "period_start", label: "Quarter", format: (v) => describePeriod({ signal_frequency: "Q", signal_period_start: v }) },
    { key: "n", label: cohort ? "Hires" : "Person-months", num: true, format: (v) => num(v) },
    { key: "events", label: "Left", num: true },
    { key: "event_rate", label: "Rate", num: true, format: (v) => pct(v, 2) },
    { key: "signal_mean", label: "Signal", num: true, format: (v) => num(v, 2) },
  ], cells, { caption: "Country-quarter points" }));
}

function drawAssociations(rows) {
  const o = objective();
  const within = rows.filter((r) => r.model === "within_country");
  const title = (id) => meta.signals.find((s) => s.indicator_id === id)?.title.split(",")[0] ?? id;
  const ci = (r) => (r.odds_ratio === null ? "not fitted" : `${r.odds_ratio.toFixed(2)} (${r.ci_low.toFixed(2)}–${r.ci_high.toFixed(2)})`);
  const verdict = (r) => (r.q_value === null ? r.note || "not fitted"
    : r.q_value < 0.05 ? "Associated, after correction" : r.p_value < 0.05 ? "Nominal only; not significant after correction" : "No evidence");
  const table = within.map((r) => ({ ...r, naive: rows.find((x) => x.model === "naive" && x.indicator_id === r.indicator_id) }));
  $("assoc-lede").textContent = `Outcome: ${within[0]?.outcome ?? o.name}. Odds ratio per one typical within-country swing of the signal; 1.00 means no effect. "Within country" compares each country only with itself and removes a common time trend.`;
  $("assoc-table").replaceChildren(dataTable([
    { key: "indicator_id", label: "Signal", format: title },
    { key: "naive", label: "Naive OR (95% CI)", format: (v) => (v ? ci(v) : "–") },
    { key: "odds_ratio", label: "Within country OR (95% CI)", format: (_, r) => ci(r) },
    { key: "q_value", label: "q", num: true, format: (v) => (v === null ? "–" : v.toFixed(2)) },
    { key: "p_value", label: "Verdict", format: (_, r) => verdict(r) },
  ], table, { caption: "Association tests", selected: (r) => r.indicator_id === state.signal }));
  const significant = within.filter((r) => r.q_value !== null && r.q_value < 0.05);
  const events = within[0]?.n_events ?? 0;
  $("assoc-verdict").textContent = significant.length
    ? `${significant.length} signal(s) remain associated after correcting for multiple tests. This is an association, not a cause.`
    : `No signal is associated with this objective after correcting for multiple tests. With ${events} events, only moderate-to-large effects could have been detected: no evidence of an effect is not evidence of no effect.`;
}

// ------------------------------------------------------------------ trust
function drawTrust() {
  const title = (id) => meta.signals.find((s) => s.indicator_id === id)?.title.split(",")[0] ?? id;
  $("freshness-table").replaceChildren(dataTable([
    { key: "indicator_id", label: "Signal", format: title },
    { key: "frequency", label: "Freq." },
    { key: "first_period", label: "Coverage", format: (v, r) => `${v.slice(0, 7)} → ${r.last_period.slice(0, 7)}` },
    { key: "countries", label: "Countries", num: true },
    { key: "gaps", label: "Gaps", num: true },
    { key: "source_updated", label: "Provider updated", format: (v) => (v ? v.slice(0, 10) : "–") },
    { key: "flag_labels", label: "Provider flags", format: (v, r) => (v ? `${r.flagged_values} × ${v}` : "none") },
  ], trust.freshness.filter((r) => meta.signals.some((s) => s.indicator_id === r.indicator_id)),
  { caption: "External data freshness" }));
  const w = trust.workforce;
  const hits = trust.quality_rules.filter((r) => r.rows_affected > 0);
  $("workforce-counts").textContent = `${num(w.employees)} employees after de-duplication; ${num(w.measurable)} measurable; ${num(w.in_country_scope)} with a known country. Nothing is dropped silently; ${trust.quality_rules.length - hits.length} further rules were checked with no rows affected.`;
  $("quality-table").replaceChildren(dataTable([
    { key: "description", label: "Rule" },
    { key: "domain", label: "Data" },
    { key: "severity", label: "Effect", format: (v) => SEVERITY[v] || v },
    { key: "rows_affected", label: "Rows", num: true },
  ], hits, { caption: "Quality rules with affected rows" }));
  const labels = { signals: "External signals", associations: "Association tests", intervals: "Uncertainty" };
  $("definitions").replaceChildren(...Object.entries(trust.definitions).flatMap(([k, v]) => [
    h("dt", { text: labels[k] || meta.objectives.find((o) => o.objective_id === k)?.name || k }), h("dd", { text: v })]));
  $("providers").replaceChildren(...trust.providers.map((p) => h("li", {}, [
    h("span", { text: `${p.name}: ` }), h("a", { href: p.terms_url, text: p.licence, rel: "noopener" })])));
}

// ------------------------------------------------------------------ theme & boot
function setupTheme() {
  const button = $("theme-toggle");
  const apply = (theme) => {
    if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
    const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    button.setAttribute("aria-pressed", String(dark));
    button.textContent = dark ? "Light theme" : "Dark theme";
    drawAll();
  };
  let saved = null;
  try { saved = localStorage.getItem("asteria-theme"); } catch { /* storage unavailable */ }
  apply(saved);
  button.addEventListener("click", () => {
    const next = button.getAttribute("aria-pressed") === "true" ? "light" : "dark";
    try { localStorage.setItem("asteria-theme", next); } catch { /* storage unavailable */ }
    apply(next);
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => drawAll());
}

async function boot() {
  try {
    const health = await api("health");
    if (health.status !== "ok") throw new ApiError("not_ready", health.detail);
    meta = await api("meta");
  } catch (error) {
    showBanner(error);
    $("main").setAttribute("aria-busy", "false");
    return;
  }
  $("as-of").textContent = meta.as_of_date;
  readUrl();
  buildFilters();
  let timer = null;
  new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(drawAll, 150); }).observe($("main"));
  await refresh();
}

$("banner-retry").addEventListener("click", () => (meta ? refresh() : boot()));
setupTheme();
boot();
