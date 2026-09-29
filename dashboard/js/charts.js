// Small SVG chart kit: time-series line (with interval band and target) and scatter.
// No dependencies. All text goes through textContent; every chart is keyboard-operable
// (focus it, then use the arrow keys) and mirrors its tooltip into an aria-live region.

const NS = "http://www.w3.org/2000/svg";

export function svgEl(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

export function h(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") node.textContent = v;
    else if (k === "class") node.className = v;
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of [].concat(children)) if (child) node.appendChild(child);
  return node;
}

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function niceTicks(min, max, count = 5) {
  if (min === max) { min -= 1; max += 1; }
  const step0 = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(+v.toFixed(10));
  return { ticks, lo: ticks[0], hi: ticks[ticks.length - 1] };
}

const linear = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);

function yearTicks(x0, x1) {
  const out = [];
  for (let y = x0.getUTCFullYear(); y <= x1.getUTCFullYear() + 1; y++) {
    const d = Date.UTC(y, 0, 1);
    if (d >= x0.getTime() && d <= x1.getTime()) out.push(new Date(d));
  }
  return out;
}

function tooltipBox(container) {
  let tip = container.querySelector(".tooltip");
  if (!tip) { tip = h("div", { class: "tooltip", hidden: true }); container.appendChild(tip); }
  return tip;
}

function fillTooltip(tip, head, rows) {
  tip.replaceChildren(h("div", { class: "t-head", text: head }));
  for (const r of rows) {
    const key = r.color ? h("span", { class: "key-line", style: `background:${r.color}` }) : null;
    tip.appendChild(h("div", { class: "t-row" }, [key, h("strong", { text: r.value }), h("span", { text: r.label })]));
  }
}

function place(tip, container, px, py) {
  tip.hidden = false;
  const box = container.getBoundingClientRect();
  const w = tip.offsetWidth;
  const left = px + 14 + w > box.width ? px - w - 14 : px + 14;
  tip.style.left = `${Math.max(0, left)}px`;
  tip.style.top = `${Math.max(0, py - 10)}px`;
}

function announce(text) {
  const live = document.getElementById("live");
  if (live) live.textContent = text;
}

/**
 * Time-series chart.
 * opts: { series: [{ id, label, color, points: [{ x: Date, y, lo?, hi?, hollow?, extra? }] }],
 *         target?: { value, label }, yFormat, xFormat, step?, band?, ariaLabel, height? }
 */
export function lineChart(container, opts) {
  container.replaceChildren();
  const width = Math.max(320, container.clientWidth || 600);
  const height = opts.height || Math.round(Math.min(380, Math.max(260, width * 0.42)));
  const m = { t: 14, r: opts.series.length <= 4 ? 84 : 16, b: 30, l: 52 };
  const all = opts.series.flatMap((s) => s.points);
  const xs = [...new Set(all.map((p) => p.x.getTime()))].sort((a, b) => a - b).map((t) => new Date(t));
  if (!xs.length) return;
  const vals = all.flatMap((p) => [p.y, p.lo, p.hi]).filter((v) => v !== null && v !== undefined);
  if (opts.target) vals.push(opts.target.value);
  const span = Math.max(...vals) - Math.min(...vals) || 1;
  const yt = niceTicks(Math.min(...vals) - span * 0.08, Math.max(...vals) + span * 0.08);
  const x = linear(xs[0].getTime(), xs[xs.length - 1].getTime(), m.l, width - m.r);
  const y = linear(yt.lo, yt.hi, height - m.b, m.t);

  const svg = svgEl("svg", {
    viewBox: `0 0 ${width} ${height}`, role: "group", "aria-roledescription": "chart",
    "aria-label": opts.ariaLabel, tabindex: 0,
  }, null);
  container.appendChild(svg);
  const grid = cssVar("--grid"), axis = cssVar("--axis"), muted = cssVar("--muted"), ink2 = cssVar("--ink-2");
  const surface = cssVar("--surface");

  for (const t of yt.ticks) {
    svgEl("line", { x1: m.l, x2: width - m.r, y1: y(t), y2: y(t), stroke: grid, "stroke-width": 1 }, svg);
    svgEl("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", "font-size": 11, fill: muted }, svg)
      .textContent = opts.yFormat(t);
  }
  svgEl("line", { x1: m.l, x2: width - m.r, y1: height - m.b, y2: height - m.b, stroke: axis }, svg);
  const xTicks = yearTicks(xs[0], xs[xs.length - 1]);
  for (const t of (xTicks.length ? xTicks : [xs[0]])) {
    svgEl("text", { x: x(t.getTime()), y: height - m.b + 18, "text-anchor": "middle", "font-size": 11, fill: muted }, svg)
      .textContent = String(t.getUTCFullYear());
  }

  if (opts.target) {
    const ty = y(opts.target.value);
    svgEl("line", { x1: m.l, x2: width - m.r, y1: ty, y2: ty, stroke: ink2, "stroke-width": 1 }, svg);
    svgEl("text", { x: m.l + 4, y: ty - 5, "font-size": 11, fill: ink2 }, svg).textContent = opts.target.label;
  }

  const pathFor = (pts, key) => {
    let d = "", open = false, prev = null;
    for (const p of pts) {
      const v = p[key];
      if (v === null || v === undefined) { open = false; continue; }
      const px = x(p.x.getTime()), py = y(v);
      if (!open) d += `M${px},${py}`;
      else d += opts.step ? `H${px}V${py}` : `L${px},${py}`;
      open = true; prev = p;
    }
    return d;
  };

  for (const s of opts.series) {
    if (opts.band) {
      // One closed band per run of consecutive points that have an interval.
      let run = [];
      const flush = () => {
        if (run.length > 1) {
          const top = run.map((p) => `${x(p.x.getTime())},${y(p.hi)}`).join("L");
          const bottom = run.slice().reverse().map((p) => `${x(p.x.getTime())},${y(p.lo)}`).join("L");
          svgEl("path", { d: `M${top}L${bottom}Z`, fill: s.color, "fill-opacity": 0.1 }, svg);
        }
        run = [];
      };
      for (const p of s.points) (p.lo !== null && p.lo !== undefined && p.hi !== null) ? run.push(p) : flush();
      flush();
    }
    svgEl("path", { d: pathFor(s.points, "y"), fill: "none", stroke: s.color, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    if (s.points.length <= 30) {
      for (const p of s.points) {
        if (p.y === null || p.y === undefined) continue;
        svgEl("circle", { cx: x(p.x.getTime()), cy: y(p.y), r: 4, fill: p.hollow ? surface : s.color,
          stroke: p.hollow ? s.color : surface, "stroke-width": 2 }, svg);
      }
    }
    if (opts.series.length <= 4) {
      const last = [...s.points].reverse().find((p) => p.y !== null && p.y !== undefined);
      if (last) {
        svgEl("text", { x: x(last.x.getTime()) + 8, y: y(last.y) + 4, "font-size": 11, fill: cssVar("--ink") }, svg)
          .textContent = opts.series.length > 1 ? `${s.label} ${opts.yFormat(last.y)}` : opts.yFormat(last.y);
      }
    }
  }

  // Crosshair: snaps to the nearest period; one tooltip lists every series.
  const cross = svgEl("line", { y1: m.t, y2: height - m.b, stroke: axis, "stroke-width": 1, visibility: "hidden" }, svg);
  const tip = tooltipBox(container);
  let index = xs.length - 1;
  const show = (i) => {
    index = Math.max(0, Math.min(xs.length - 1, i));
    const t = xs[index].getTime();
    const cx = x(t);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    const rows = opts.series.map((s) => {
      const p = s.points.find((q) => q.x.getTime() === t);
      return { color: s.color, label: p && p.extra ? `${s.label} · ${p.extra}` : s.label,
        value: p && p.y !== null && p.y !== undefined ? opts.yFormat(p.y) : "no value" };
    });
    const head = opts.xFormat(xs[index]);
    fillTooltip(tip, head, rows);
    const scale = svg.getBoundingClientRect().width / width;
    place(tip, container, cx * scale, m.t * scale);
    announce(`${head}: ${rows.map((r) => `${r.label} ${r.value}`).join("; ")}`);
  };
  const hide = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); };
  const overlay = svgEl("rect", { x: m.l, y: m.t, width: width - m.l - m.r, height: height - m.t - m.b,
    fill: "transparent" }, svg);
  overlay.addEventListener("pointermove", (e) => {
    const rect = svg.getBoundingClientRect();
    const px = (e.clientX - rect.left) * (width / rect.width);
    let best = 0;
    xs.forEach((d, i) => { if (Math.abs(x(d.getTime()) - px) < Math.abs(x(xs[best].getTime()) - px)) best = i; });
    show(best);
  });
  overlay.addEventListener("pointerleave", hide);
  svg.addEventListener("focus", () => show(index));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { show(index + 1); e.preventDefault(); }
    if (e.key === "ArrowLeft") { show(index - 1); e.preventDefault(); }
    if (e.key === "Escape") hide();
  });
}

/**
 * Scatter with sample-size-scaled dots and emphasis.
 * opts: { points: [{ x, y, n, emphasis, label, detail }], xFormat, yFormat, xLabel, yLabel, ariaLabel }
 */
export function scatterChart(container, opts) {
  container.replaceChildren();
  if (!opts.points.length) return;
  const width = Math.max(320, container.clientWidth || 600);
  const height = Math.round(Math.min(420, Math.max(280, width * 0.45)));
  const m = { t: 14, r: 16, b: 44, l: 56 };
  const xt = niceTicks(Math.min(...opts.points.map((p) => p.x)), Math.max(...opts.points.map((p) => p.x)));
  const yt = niceTicks(0, Math.max(...opts.points.map((p) => p.y)) * 1.05 || 0.01);
  const x = linear(xt.lo, xt.hi, m.l, width - m.r);
  const y = linear(yt.lo, yt.hi, height - m.b, m.t);
  const maxN = Math.max(...opts.points.map((p) => p.n));
  const radius = (n) => 4 + 8 * Math.sqrt(n / maxN);

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "group", "aria-roledescription": "chart",
    "aria-label": opts.ariaLabel, tabindex: 0 });
  container.appendChild(svg);
  const grid = cssVar("--grid"), muted = cssVar("--muted"), surface = cssVar("--surface");
  for (const t of yt.ticks) {
    svgEl("line", { x1: m.l, x2: width - m.r, y1: y(t), y2: y(t), stroke: grid }, svg);
    svgEl("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end", "font-size": 11, fill: muted }, svg).textContent = opts.yFormat(t);
  }
  for (const t of xt.ticks) {
    svgEl("text", { x: x(t), y: height - m.b + 16, "text-anchor": "middle", "font-size": 11, fill: muted }, svg).textContent = opts.xFormat(t);
  }
  svgEl("text", { x: (m.l + width - m.r) / 2, y: height - 6, "text-anchor": "middle", "font-size": 11, fill: cssVar("--ink-2") }, svg).textContent = opts.xLabel;
  svgEl("text", { x: 12, y: m.t + (height - m.t - m.b) / 2, "text-anchor": "middle", "font-size": 11, fill: cssVar("--ink-2"),
    transform: `rotate(-90 12 ${m.t + (height - m.t - m.b) / 2})` }, svg).textContent = opts.yLabel;

  const ordered = [...opts.points].sort((a, b) => (a.emphasis === b.emphasis ? 0 : a.emphasis ? 1 : -1));
  for (const p of ordered) {
    svgEl("circle", { cx: x(p.x), cy: y(p.y), r: radius(p.n),
      fill: p.emphasis ? cssVar("--accent") : cssVar("--de-emphasis"),
      "fill-opacity": p.emphasis ? 0.75 : 0.6, stroke: surface, "stroke-width": 2 }, svg);
  }

  const ring = svgEl("circle", { r: 0, fill: "none", stroke: cssVar("--ink"), "stroke-width": 1.5, visibility: "hidden" }, svg);
  const tip = tooltipBox(container);
  const byX = [...opts.points].sort((a, b) => a.x - b.x);
  let index = 0;
  const show = (p) => {
    index = byX.indexOf(p);
    ring.setAttribute("cx", x(p.x)); ring.setAttribute("cy", y(p.y));
    ring.setAttribute("r", radius(p.n) + 3); ring.setAttribute("visibility", "visible");
    fillTooltip(tip, p.label, p.detail);
    const scale = svg.getBoundingClientRect().width / width;
    place(tip, container, x(p.x) * scale, y(p.y) * scale);
    announce(`${p.label}: ${p.detail.map((r) => `${r.label} ${r.value}`).join("; ")}`);
  };
  const hide = () => { tip.hidden = true; ring.setAttribute("visibility", "hidden"); };
  const overlay = svgEl("rect", { x: m.l, y: m.t, width: width - m.l - m.r, height: height - m.t - m.b, fill: "transparent" }, svg);
  overlay.addEventListener("pointermove", (e) => {
    const rect = svg.getBoundingClientRect();
    const k = width / rect.width;
    const px = (e.clientX - rect.left) * k, py = (e.clientY - rect.top) * k;
    let best = null, dist = 24 * k;  // nearest point within a 24px hit radius
    for (const p of opts.points) {
      const d = Math.hypot(x(p.x) - px, y(p.y) - py);
      if (d < dist) { dist = d; best = p; }
    }
    best ? show(best) : hide();
  });
  overlay.addEventListener("pointerleave", hide);
  svg.addEventListener("focus", () => show(byX[index]));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { show(byX[Math.min(byX.length - 1, index + 1)]); e.preventDefault(); }
    if (e.key === "ArrowLeft") { show(byX[Math.max(0, index - 1)]); e.preventDefault(); }
    if (e.key === "Escape") hide();
  });
}

/** Accessible table. columns: [{ key, label, num?, format? }] */
export function dataTable(columns, rows, { caption, selected } = {}) {
  const table = h("table");
  if (caption) table.appendChild(h("caption", { class: "visually-hidden", text: caption }));
  const head = h("tr", {}, columns.map((c) => h("th", { scope: "col", class: c.num ? "num" : "", text: c.label })));
  table.appendChild(h("thead", {}, head));
  const body = h("tbody");
  for (const r of rows) {
    const tr = h("tr", { class: selected && selected(r) ? "selected" : "" },
      columns.map((c) => h("td", { class: c.num ? "num" : "", text: c.format ? c.format(r[c.key], r) : (r[c.key] ?? "") })));
    body.appendChild(tr);
  }
  table.appendChild(body);
  return table;
}
