/* After the Fire — static dashboard over the dbt gold tables exported to data/*.json */

const TABLES = [
  "dim_episodes", "fct_fire_activity_monthly", "fct_observations_monthly", "fct_baci_summary",
  "fct_baci_effect", "fct_species_response", "fct_species_latitude_shift", "fct_taxon_group_mix",
  "fct_map_cells",
];
const TAXON_ORDER = ["Birds", "Plants", "Insects", "Mammals", "Reptiles", "Amphibians", "Fungi", "Other"];
const ZONE_LABEL = { burned: "Burned", control: "Control" };

const state = { episode: null, timelineMode: "indexed", taxon: "All" };
const data = {};
let map, cellLayer, tileLayer;

const fmt = d3.format(",");
const fmtCompact = (v) => (Math.abs(v) >= 10000 ? d3.format(".3~s")(v).replace("G", "B") : fmt(Math.round(v)));
const fmtPct = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(0) + "%";
const fmtDate = d3.utcFormat("%b %Y");
const parseDate = (s) => new Date(s + "T00:00:00Z");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* ---------------------------------------------------------------- bootstrap */

async function init() {
  const [meta, ...tables] = await Promise.all([
    fetch("data/meta.json").then((r) => r.json()),
    ...TABLES.map((t) => fetch(`data/${t}.json`).then((r) => r.json())),
  ]);
  TABLES.forEach((t, i) => (data[t] = tables[i]));
  document.getElementById("generated-at").textContent = `Data snapshot ${meta.generated_at.slice(0, 10)}`;

  // One button per region; it opens the region's oldest fire.
  const picker = document.getElementById("region-picker");
  for (const e of data.dim_episodes.filter((d) => d.recency_rank === 1)) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = e.region_name;
    b.dataset.region = e.region_id;
    b.addEventListener("click", () => selectEpisode(oldestEpisode(e.region_id).episode_id));
    picker.appendChild(b);
  }

  document.querySelectorAll("#timeline-mode button").forEach((b) =>
    b.addEventListener("click", () => {
      state.timelineMode = b.dataset.mode;
      document.querySelectorAll("#timeline-mode button").forEach((x) =>
        x.setAttribute("aria-pressed", String(x === b)));
      renderTimeline();
    }));

  document.getElementById("taxon-filter").addEventListener("change", (e) => {
    state.taxon = e.target.value;
    renderSpecies();
  });

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch (_) {}
    renderAll();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderCharts, 150);
  });

  const fromHash = location.hash.slice(1);
  const start = data.dim_episodes.find((e) => e.episode_id === fromHash)
    || oldestEpisode(fromHash)
    || oldestEpisode(data.dim_episodes.find((e) => e.recency_rank === 1).region_id);
  selectEpisode(start.episode_id);
}

try {
  const saved = localStorage.getItem("theme");
  if (saved) document.documentElement.dataset.theme = saved;
} catch (_) {}

function selectEpisode(id) {
  state.episode = id;
  state.taxon = "All";
  const ep = episode();
  history.replaceState(null, "", "#" + id);
  document.querySelectorAll("#region-picker button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.region === ep.region_id)));
  // Every chart's "burned" series wears the selected fire's red.
  document.documentElement.style.setProperty("--burned", fireVar(ep));
  renderEpisodePicker();
  renderAll();
}

const episode = () => data.dim_episodes.find((e) => e.episode_id === state.episode);
const regionEpisodes = () => d3.sort(data.dim_episodes.filter((e) => e.region_id === episode().region_id), (e) => e.recency_rank);
const oldestEpisode = (regionId) => d3.greatest(data.dim_episodes.filter((e) => e.region_id === regionId), (e) => e.recency_rank);
const forEpisode = (table) => data[table].filter((d) => d.episode_id === state.episode);
const forRegion = (table) => data[table].filter((d) => d.region_id === episode().region_id);
// Red ramp: the most recent fire of a region is bright red, older ones dark red.
const fireVar = (ep) => `var(--fire-${Math.min(ep.recency_rank, 2)})`;
const fireColor = (ep) => css(`--fire-${Math.min(ep.recency_rank, 2)}`);
const fireYear = (ep) => ep.fire_start.slice(0, 4);

function renderEpisodePicker() {
  const eps = regionEpisodes();
  const picker = document.getElementById("episode-picker");
  document.getElementById("episode-bar").hidden = eps.length < 2;
  picker.innerHTML = "";
  for (const e of eps) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<i class="dot" style="background:${fireVar(e)}"></i>${fireYear(e)} fire`;
    b.title = e.fire_name;
    b.setAttribute("aria-pressed", String(e.episode_id === state.episode));
    b.addEventListener("click", () => selectEpisode(e.episode_id));
    picker.appendChild(b);
  }
}

function renderAll() {
  renderHeader();
  renderMap();
  renderCharts();
}

function renderCharts() {
  renderTimeline();
  renderVerdict();
  renderSpecies();
  renderMix();
  renderLatitude();
}

/* ---------------------------------------------------------------- tooltip */

const tip = document.getElementById("tooltip");
function showTip(event, html) {
  tip.innerHTML = html;
  tip.style.opacity = 1;
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = event.clientX + pad, y = event.clientY + pad;
  if (x + w > innerWidth - 8) x = event.clientX - w - pad;
  if (y + h > innerHeight - 8) y = event.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
const hideTip = () => (tip.style.opacity = 0);
const tipRow = (label, value, color) =>
  `<div class="t-row"><span>${color ? `<i class="key" style="background:${color}"></i>` : ""}${label}</span><b>${value}</b></div>`;

/* ---------------------------------------------------------------- 1. header, KPIs, map */

const monthsSpan = (a, b) => Math.max(1, Math.round((parseDate(b) - parseDate(a)) / (30.44 * 864e5)));

function periodSentence(r) {
  const after = monthsSpan(r.after_start, r.after_end);
  if (!r.is_season_matched) {
    return `We compare the ${monthsSpan(r.before_start, r.before_end)} months before with the ${after} months after.`;
  }
  const span = `${d3.utcFormat("%B")(parseDate(r.after_start))}–${d3.utcFormat("%B")(parseDate(r.after_end))}`;
  return `The fire is recent: only ${after} month${after > 1 ? "s" : ""} of "after" so far. ` +
    `To avoid comparing one season with a whole year, "before" keeps the same season (${span}) ` +
    `of the ${Math.round(monthsSpan(r.before_start, r.before_end) / 12)} previous years.`;
}

function renderHeader() {
  const r = episode();
  const fs = parseDate(r.fire_start), fe = parseDate(r.fire_end);
  document.getElementById("fire-title").textContent = `${r.fire_name}, ${r.region_name}`;
  document.getElementById("fire-lede").textContent =
    `Fire from ${d3.utcFormat("%-d %B %Y")(fs)} to ${d3.utcFormat("%-d %B %Y")(fe)}. ` + periodSentence(r);

  const kpis = [
    { label: "Burned area", value: `${fmt(r.burned_area_km2)} km²`, note: `${fmt(r.n_burned_cells)} hexagons` },
    { label: "Fire detections", value: fmtCompact(r.n_fire_detections), note: "VIIRS, during the event" },
    { label: "Observations", value: fmtCompact(r.n_observations), note: `from ${r.n_datasets} datasets` },
    { label: "Species observed", value: fmt(r.n_species), note: "over the study window" },
  ];
  document.getElementById("kpis").innerHTML = kpis.map((k) =>
    `<div class="kpi"><div class="label">${k.label}</div><div class="value">${k.value}</div><div class="note">${k.note}</div></div>`
  ).join("");
}

function renderMap() {
  const r = episode();
  const dark = css("color-scheme") === "dark";
  if (!map) {
    map = L.map("map", { preferCanvas: true, scrollWheelZoom: false, attributionControl: true });
  }
  // Esri basemaps, free with attribution, no API key: Ocean (light-blue sea) in light mode, dark gray in dark mode.
  const tiles = dark
    ? "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
    : "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}";
  if (tileLayer) tileLayer.remove();
  tileLayer = L.tileLayer(tiles, {
    attribution: dark
      ? "Basemap &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
      : "Basemap &copy; Esri, GEBCO, NOAA, National Geographic, Garmin, HERE",
    maxNativeZoom: dark ? 16 : 13,
    maxZoom: 16,
  }).addTo(map);

  if (cellLayer) cellLayer.remove();
  cellLayer = L.layerGroup().addTo(map);
  const eps = regionEpisodes();
  const byId = new Map(eps.map((e) => [e.episode_id, e]));
  const color = { control: css("--control"), buffer: css("--excluded"), disturbed: css("--excluded") };
  const surface = css("--surface");

  document.getElementById("map-legend").innerHTML =
    eps.map((e) => `<span><i class="swatch" style="background:${fireVar(e)}"></i>Burned in ${fireYear(e)}</span>`).join("") +
    `<span><i class="swatch" style="background:var(--control)"></i>Control (unburned)</span>` +
    `<span><i class="swatch" style="background:var(--excluded)"></i>Excluded: buffer around the ${fireYear(r)} scar, or other fire</span>`;

  for (const c of forEpisode("fct_map_cells")) {
    const boundary = h3.cellToBoundary(c.h3_index);
    const lastFire = c.last_burned_episode_id && byId.get(c.last_burned_episode_id);
    const title = c.burned_episodes ? `Burned in ${c.burned_episodes}`
      : c.zone === "buffer" ? "Buffer (excluded)" : c.zone === "disturbed" ? "Other fire (excluded)" : "Control cell";
    const poly = L.polygon(boundary, {
      color: surface, weight: 0.6,
      fillColor: lastFire ? fireColor(lastFire) : color[c.zone],
      fillOpacity: lastFire ? 0.75 : c.zone === "control" ? 0.45 : 0.5,
    });
    poly.on("mousemove", (e) => showTip(e.originalEvent,
      `<div class="t-title">${title}</div>` +
      tipRow(`Role in the ${fireYear(r)} analysis`, { burned: "burned", control: "control" }[c.zone] || "excluded") +
      tipRow(`Fire detections in ${fireYear(r)}`, fmt(c.n_fire_detections)) +
      tipRow("Observations before", fmt(c.n_obs_before)) +
      tipRow("Observations after", fmt(c.n_obs_after)) +
      tipRow("Species before → after", `${c.n_species_before} → ${c.n_species_after}`)));
    poly.on("mouseout", hideTip);
    cellLayer.addLayer(poly);
  }
  map.fitBounds([[r.min_lat, r.min_lon], [r.max_lat, r.max_lon]]);
}

/* ---------------------------------------------------------------- shared chart helpers */

function svgFor(id, height, margin) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  const width = Math.max(280, el.clientWidth);
  const svg = d3.select(el).append("svg").attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);
  return { el, svg, width, height, inner: { w: width - margin.left - margin.right, h: height - margin.top - margin.bottom },
    g: svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`) };
}

// Column with a 4px rounded top, square at the baseline.
function roundedTop(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}
// Horizontal bar from x0 to x1 with a rounded end away from the baseline x0.
function roundedEnd(x0, x1, y, h, r = 4) {
  const dir = x1 >= x0 ? 1 : -1, len = Math.abs(x1 - x0);
  if (len < 0.5) return "";
  r = Math.min(r, h / 2, len);
  const xe = x1 - dir * r;
  return `M${x0},${y}H${xe}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${xe},${y + h}H${x0}Z`;
}

function monthsBetween(start, end) {
  return d3.utcMonth.range(d3.utcMonth.floor(start), d3.utcMonth.offset(d3.utcMonth.floor(end), 1));
}

/* ---------------------------------------------------------------- 2. timeline */

function renderTimeline() {
  const r = episode();
  const months = monthsBetween(parseDate(r.before_start), parseDate(r.after_end));
  const fs = parseDate(r.fire_start), fe = parseDate(r.fire_end);
  const rows = forEpisode("fct_observations_monthly");

  const series = ["burned", "control"].map((zone) => {
    const byMonth = new Map(rows.filter((d) => d.zone === zone).map((d) => [d.month, d.n_observations]));
    const values = months.map((m) => ({ month: m, raw: byMonth.get(m.toISOString().slice(0, 10)) || 0 }));
    const base = d3.mean(values.filter((v) => v.month < fs), (v) => v.raw) || 1;
    values.forEach((v) => (v.indexed = (v.raw / base) * 100));
    return { zone, values };
  });
  const key = state.timelineMode;

  const margin = { top: 12, right: 70, bottom: 26, left: 48 };
  const { svg, g, inner, width } = svgFor("chart-timeline", 260, margin);
  const x = d3.scaleUtc().domain([months[0], months[months.length - 1]]).range([0, inner.w]);
  const y = d3.scaleLinear().domain([0, d3.max(series, (s) => d3.max(s.values, (v) => v[key])) || 1]).nice().range([inner.h, 0]);

  // A band per fire of the region, in its own red; the selected one is labelled bolder.
  for (const e of regionEpisodes()) {
    const s0 = parseDate(e.fire_start), s1 = parseDate(e.fire_end);
    if (s1 < months[0] || s0 > months[months.length - 1]) continue;
    const x0 = Math.max(0, x(d3.utcMonth.floor(s0)));
    g.append("rect").attr("x", x0).attr("width", Math.max(3, Math.min(inner.w, x(s1)) - x0))
      .attr("y", 0).attr("height", inner.h).attr("fill", fireVar(e)).attr("fill-opacity", 0.14);
    g.append("text").attr("x", x0 + 4).attr("y", 10)
      .attr("class", e.episode_id === r.episode_id ? "label-strong" : "label-mid").text(`${fireYear(e)} fire`);
  }

  g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(5).tickSize(-inner.w).tickFormat(""));
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(8)
    .tickFormat(key === "indexed" ? d3.format("d") : fmtCompact));
  g.append("g").attr("class", "axis").attr("transform", `translate(0,${inner.h})`)
    .call(width < 600
      ? d3.axisBottom(x).ticks(d3.utcYear.every(1)).tickSizeOuter(0).tickFormat(d3.utcFormat("%Y"))
      : d3.axisBottom(x).ticks(8).tickSizeOuter(0).tickFormat(d3.utcFormat("%b %Y")));
  if (key === "indexed") {
    g.append("line").attr("x1", 0).attr("x2", inner.w).attr("y1", y(100)).attr("y2", y(100))
      .attr("stroke", "var(--axis)").attr("stroke-width", 1);
  }

  const line = d3.line().x((v) => x(v.month)).y((v) => y(v[key])).curve(d3.curveMonotoneX);
  for (const s of series) {
    g.append("path").datum(s.values).attr("fill", "none").attr("stroke", `var(--${s.zone})`)
      .attr("stroke-width", 2).attr("stroke-linejoin", "round").attr("stroke-linecap", "round").attr("d", line);
  }
  // End labels, with leader-free nudge only when far enough apart
  const ends = series.map((s) => ({ zone: s.zone, y: y(s.values[s.values.length - 1][key]) }));
  if (Math.abs(ends[0].y - ends[1].y) >= 14) {
    for (const e of ends) {
      g.append("text").attr("x", inner.w + 8).attr("y", e.y + 4).attr("class", "label-mid").text(ZONE_LABEL[e.zone]);
    }
  }

  // Crosshair + tooltip
  const cross = g.append("line").attr("y1", 0).attr("y2", inner.h).attr("stroke", "var(--axis)").style("opacity", 0);
  const dots = series.map((s) => g.append("circle").attr("r", 4.5).attr("fill", `var(--${s.zone})`)
    .attr("stroke", "var(--surface)").attr("stroke-width", 2).style("opacity", 0));
  g.append("rect").attr("width", inner.w).attr("height", inner.h).attr("fill", "transparent")
    .on("mousemove", (event) => {
      const [mx] = d3.pointer(event);
      const i = d3.bisectCenter(months.map((m) => +m), +x.invert(mx));
      const m = months[i];
      cross.attr("x1", x(m)).attr("x2", x(m)).style("opacity", 1);
      series.forEach((s, j) => dots[j].attr("cx", x(m)).attr("cy", y(s.values[i][key])).style("opacity", 1));
      showTip(event, `<div class="t-title">${fmtDate(m)}</div>` + series.map((s) =>
        tipRow(ZONE_LABEL[s.zone], key === "indexed"
          ? `${Math.round(s.values[i].indexed)} <span style="font-weight:400">(${fmt(s.values[i].raw)})</span>`
          : fmt(s.values[i].raw), css(`--${s.zone}`))).join(""));
    })
    .on("mouseleave", () => { cross.style("opacity", 0); dots.forEach((d) => d.style("opacity", 0)); hideTip(); });

  renderFireColumns(months, x, margin);
}

function renderFireColumns(months, xTimeline, marginTimeline) {
  const byMonth = new Map(forRegion("fct_fire_activity_monthly").map((d) => [d.month, d]));
  const values = months.map((m) => ({ month: m, n: byMonth.get(m.toISOString().slice(0, 10))?.n_detections || 0 }));
  const { g, inner } = svgFor("chart-fire", 130, { ...marginTimeline, top: 8 });
  const x = xTimeline.copy().range([0, inner.w]);
  const y = d3.scaleLinear().domain([0, d3.max(values, (v) => v.n) || 1]).nice().range([inner.h, 0]);
  const colW = Math.max(1, Math.min(24, inner.w / months.length - 2));

  g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(3).tickSize(-inner.w).tickFormat(""));
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(3).tickSize(0).tickPadding(8).tickFormat(fmtCompact));
  g.append("g").attr("class", "axis").attr("transform", `translate(0,${inner.h})`)
    .call(d3.axisBottom(x).ticks(0).tickSizeOuter(0));
  const fireOf = (m) => regionEpisodes().find((e) =>
    m <= parseDate(e.fire_end) && d3.utcMonth.offset(m, 1) > parseDate(e.fire_start));

  g.selectAll("path.col").data(values).join("path").attr("class", "col")
    .attr("d", (v) => roundedTop(x(v.month) - colW / 2, y(v.n), colW, inner.h - y(v.n), Math.min(4, colW / 2)))
    .attr("fill", (v) => (fireOf(v.month) ? fireVar(fireOf(v.month)) : "var(--neutral-mark-2)"));
  g.selectAll("rect.hit").data(values).join("rect").attr("class", "hit")
    .attr("x", (v) => x(v.month) - inner.w / months.length / 2).attr("width", inner.w / months.length)
    .attr("y", 0).attr("height", inner.h).attr("fill", "transparent")
    .on("mousemove", (event, v) => showTip(event, `<div class="t-title">${fmtDate(v.month)}</div>` + tipRow("Fire detections", fmt(v.n))))
    .on("mouseleave", hideTip);
}

/* ---------------------------------------------------------------- 3. verdict */

function renderVerdict() {
  const summary = forEpisode("fct_baci_summary");
  const effects = forEpisode("fct_baci_effect");
  const effect = (m) => effects.find((e) => e.metric === m);

  const n = summary[0]?.n_rarefaction;
  document.getElementById("rarefaction-note").textContent = n ? `Expected species in ${fmt(n)} random observations` : "";
  slopeChart("chart-slope-richness", summary, "rarefied_richness", (v) => v.toFixed(0));
  slopeChart("chart-slope-obs", summary, "n_observations", fmtCompact);

  const rich = effect("rarefied_richness");
  const card = document.getElementById("verdict-card");
  if (!rich || rich.baci_effect_pct == null) {
    card.innerHTML = `<h3>BACI effect</h3><p class="empty">Not enough observations in one of the four boxes.</p>`;
    return;
  }
  if (rich.is_reliable === false) {
    card.innerHTML = `
      <h3>BACI effect on richness</h3>
      <div class="hero-figure">Too early</div>
      <p class="hero-caption">One of the four boxes has only ${fmt(rich.smallest_box_observations)} observations
        (at least 100 needed). The burned area is rarely visited, and recent records reach GBIF with a delay
        of weeks to a year (eBird publishes yearly). The numbers on the left are shown for transparency, not as a result.</p>`;
    return;
  }
  const v = rich.baci_effect_pct;
  const cls = v <= -5 ? "down" : v >= 5 ? "up" : "";
  const sentence = Math.abs(v) < 5
    ? "The burned area kept pace with the control: no clear change in species richness."
    : v < 0
      ? `After the fire, the burned area shows ${Math.abs(v).toFixed(0)}% lower species richness than expected from the control's trajectory.`
      : `After the fire, the burned area shows ${v.toFixed(0)}% higher species richness than expected from the control's trajectory.`;
  const row = (label, m) => {
    const e = effect(m);
    return e && e.baci_effect_pct != null ? `<div><span>${label}</span><span>${fmtPct(e.baci_effect_pct)}</span></div>` : "";
  };
  card.innerHTML = `
    <h3>BACI effect on richness</h3>
    <div class="hero-figure ${cls}">${fmtPct(v)}</div>
    <p class="hero-caption">${sentence}</p>
    <div class="mini-effects">
      ${row("Observations (effort)", "n_observations")}
      ${row("Raw species count", "n_species")}
      ${row("Rarefied richness", "rarefied_richness")}
    </div>`;
}

function slopeChart(id, summary, metric, format) {
  const margin = { top: 16, right: 92, bottom: 26, left: 40 };
  const { g, inner } = svgFor(id, 220, margin);
  const periods = ["before", "after"];
  const x = d3.scalePoint().domain(periods).range([0, inner.w]).padding(0.15);
  const vals = summary.map((d) => d[metric]);
  if (!vals.length) { g.append("text").text("No data"); return; }
  const y = d3.scaleLinear().domain([0, d3.max(vals)]).nice().range([inner.h, 0]);

  g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(4).tickSize(-inner.w).tickFormat(""));
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(8).tickFormat(fmtCompact));
  g.append("g").attr("class", "axis").attr("transform", `translate(0,${inner.h})`)
    .call(d3.axisBottom(x).tickSize(0).tickPadding(8).tickFormat((p) => (p === "before" ? "Before" : "After")));

  const zones = ["control", "burned"];
  const ends = [];
  for (const zone of zones) {
    const pts = periods.map((p) => summary.find((d) => d.zone === zone && d.period === p)).filter(Boolean);
    if (pts.length < 2) continue;
    g.append("path").attr("d", d3.line().x((d) => x(d.period)).y((d) => y(d[metric]))(pts))
      .attr("stroke", `var(--${zone})`).attr("stroke-width", 2).attr("fill", "none");
    g.selectAll(null).data(pts).join("circle")
      .attr("cx", (d) => x(d.period)).attr("cy", (d) => y(d[metric])).attr("r", 5)
      .attr("fill", `var(--${zone})`).attr("stroke", "var(--surface)").attr("stroke-width", 2)
      .on("mousemove", (event, d) => showTip(event,
        `<div class="t-title">${ZONE_LABEL[zone]}, ${d.period}</div>` +
        tipRow("Observations", fmt(d.n_observations)) + tipRow("Species (raw)", fmt(d.n_species)) +
        tipRow("Rarefied richness", d.rarefied_richness.toFixed(1)) + tipRow("Cells observed", fmt(d.n_cells_observed))))
      .on("mouseleave", hideTip);
    ends.push({ zone, y: y(pts[1][metric]), value: pts[1][metric] });
  }
  // Direct end labels; separate them when they collide
  ends.sort((a, b) => a.y - b.y);
  if (ends.length === 2 && ends[1].y - ends[0].y < 28) {
    const mid = (ends[0].y + ends[1].y) / 2;
    ends[0].ly = mid - 14; ends[1].ly = mid + 14;
  }
  for (const e of ends) {
    const ly = e.ly ?? e.y;
    const t = g.append("text").attr("x", x("after") + 10).attr("y", ly - 2);
    t.append("tspan").attr("class", "label-strong").text(format(e.value));
    t.append("tspan").attr("x", x("after") + 10).attr("dy", 13).attr("class", "label-mid").text(ZONE_LABEL[e.zone]);
  }
}

/* ---------------------------------------------------------------- 4. species */

function renderSpecies() {
  const all = forEpisode("fct_species_response");
  const select = document.getElementById("taxon-filter");
  const groups = TAXON_ORDER.filter((t) => all.some((d) => d.taxon_group === t));
  select.innerHTML = ["All", ...groups].map((g) => `<option ${g === state.taxon ? "selected" : ""}>${g}</option>`).join("");

  const scored = all.filter((d) => ["more_frequent", "less_frequent", "stable"].includes(d.response)
    && (state.taxon === "All" || d.taxon_group === state.taxon));
  const top = d3.sort(scored.filter((d) => d.baci_log2 > 0), (d) => -d.baci_log2).slice(0, 10);
  const bottom = d3.sort(scored.filter((d) => d.baci_log2 < 0), (d) => d.baci_log2).slice(0, 10);
  const rows = [...top, ...bottom.reverse()];

  const rowH = 24;
  const el = document.getElementById("chart-species");
  if (!rows.length) {
    el.innerHTML = `<p class="empty">No species with enough observations in this group.</p>`;
  } else {
    const narrow = el.clientWidth < 520;
    const margin = { top: 24, right: 16, bottom: 8, left: narrow ? 130 : 200 };
    const { g, inner } = svgFor("chart-species", rows.length * rowH + 32, margin);
    const ext = Math.max(2, d3.max(rows, (d) => Math.abs(d.baci_log2)));
    const x = d3.scaleLinear().domain([-ext, ext]).nice().range([0, inner.w]);
    const y = d3.scaleBand().domain(rows.map((d) => d.species_key)).range([0, rows.length * rowH]).padding(0.3);

    const ticks = x.ticks(narrow ? 4 : 6).filter(Number.isInteger);
    g.append("g").attr("class", "grid").selectAll("line").data(ticks).join("line")
      .attr("x1", x).attr("x2", x).attr("y1", -4).attr("y2", rows.length * rowH);
    g.selectAll("text.tick").data(ticks).join("text").attr("class", "tick")
      .attr("x", x).attr("y", -10).attr("text-anchor", "middle")
      .text((t) => (t === 0 ? "same" : t > 0 ? `×${2 ** t}` : `×1/${2 ** -t}`));
    g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", -4).attr("y2", rows.length * rowH)
      .attr("stroke", "var(--axis)");

    const barH = Math.min(14, y.bandwidth());
    g.selectAll("path.bar").data(rows).join("path").attr("class", "bar")
      .attr("d", (d) => roundedEnd(x(0), x(d.baci_log2), y(d.species_key) + (y.bandwidth() - barH) / 2, barH))
      .attr("fill", (d) => (d.baci_log2 > 0 ? "var(--neutral-mark)" : "var(--neutral-mark-2)"));
    g.selectAll("text.name").data(rows).join("text").attr("class", "name label-mid")
      .attr("x", -10).attr("y", (d) => y(d.species_key) + y.bandwidth() / 2 + 4).attr("text-anchor", "end")
      .style("font-style", (d) => (d.species_name.startsWith("Demo") ? "normal" : "italic"))
      .text((d) => truncate(d.species_name, narrow ? 18 : 28));
    g.selectAll("rect.hit").data(rows).join("rect").attr("class", "hit")
      .attr("x", -margin.left).attr("width", inner.w + margin.left).attr("y", (d) => y(d.species_key) - 3)
      .attr("height", rowH).attr("fill", "transparent")
      .on("mousemove", (event, d) => showTip(event, speciesTip(d)))
      .on("mouseleave", hideTip);
  }

  document.getElementById("table-species").innerHTML = table(
    ["Species", "Group", "Burned before", "Burned after", "Control before", "Control after", "Relative change"],
    d3.sort(scored, (d) => -d.baci_log2).map((d) => [d.species_name, d.taxon_group, fmt(d.n_burned_before),
      fmt(d.n_burned_after), fmt(d.n_control_before), fmt(d.n_control_after), ratioLabel(d.baci_log2)]));

  const fresh = d3.sort(all.filter((d) => d.response === "new_in_region"
    && (state.taxon === "All" || d.taxon_group === state.taxon)), (d) => -d.n_region_after);
  document.getElementById("new-species").innerHTML = fresh.length
    ? fresh.slice(0, 30).map((d) => `<span class="chip">${d.species_name} · <b>${d.n_region_after}</b></span>`).join("")
    : `<p class="empty">None in this group.</p>`;
}

const ratioLabel = (log2) => {
  const r = 2 ** log2;
  return r >= 1 ? `×${r.toFixed(1)}` : `×1/${(1 / r).toFixed(1)}`;
};
const truncate = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

function speciesTip(d) {
  return `<div class="t-title">${d.species_name}</div>` +
    tipRow("Group", d.taxon_group) +
    tipRow("Burned: before → after", `${fmt(d.n_burned_before)} → ${fmt(d.n_burned_after)}`, css("--burned")) +
    tipRow("Control: before → after", `${fmt(d.n_control_before)} → ${fmt(d.n_control_after)}`, css("--control")) +
    tipRow("Frequency vs control", ratioLabel(d.baci_log2));
}

function table(headers, rows) {
  return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}

/* ---------------------------------------------------------------- 5. community mix */

function renderMix() {
  const rows = forEpisode("fct_taxon_group_mix");
  const effect = forEpisode("fct_baci_effect")[0];
  document.getElementById("mix-warning").hidden = !effect || effect.is_reliable !== false;
  const groups = TAXON_ORDER.filter((t) => rows.some((d) => d.taxon_group === t));
  const share = (g, zone, period) => rows.find((d) => d.taxon_group === g && d.zone === zone && d.period === period)?.share || 0;

  const rowH = 40;
  const margin = { top: 20, right: 24, bottom: 8, left: 96 };
  const { g, inner } = svgFor("chart-mix", groups.length * rowH + 28, margin);
  const x = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.share) || 1]).nice().range([0, inner.w]);
  const y = d3.scaleBand().domain(groups).range([0, groups.length * rowH]);

  g.append("g").attr("class", "grid").selectAll("line").data(x.ticks(5)).join("line")
    .attr("x1", x).attr("x2", x).attr("y1", -4).attr("y2", groups.length * rowH);
  g.selectAll("text.tick").data(x.ticks(5)).join("text").attr("class", "tick")
    .attr("x", x).attr("y", -8).attr("text-anchor", "middle").text(d3.format(".0%"));
  g.selectAll("text.name").data(groups).join("text").attr("class", "name label-mid")
    .attr("x", -12).attr("y", (d) => y(d) + rowH / 2 + 4).attr("text-anchor", "end").text((d) => d);

  for (const [zone, dy] of [["burned", -7], ["control", 7]]) {
    for (const grp of groups) {
      const cy = y(grp) + rowH / 2 + dy;
      const b = share(grp, zone, "before"), a = share(grp, zone, "after");
      g.append("line").attr("x1", x(b)).attr("x2", x(a)).attr("y1", cy).attr("y2", cy)
        .attr("stroke", `var(--${zone})`).attr("stroke-width", 2).attr("stroke-linecap", "round");
      g.append("circle").attr("cx", x(b)).attr("cy", cy).attr("r", 4)
        .attr("fill", "var(--surface)").attr("stroke", `var(--${zone})`).attr("stroke-width", 2);
      g.append("circle").attr("cx", x(a)).attr("cy", cy).attr("r", 5)
        .attr("fill", `var(--${zone})`).attr("stroke", "var(--surface)").attr("stroke-width", 2);
    }
  }
  g.selectAll("rect.hit").data(groups).join("rect").attr("class", "hit")
    .attr("x", -margin.left).attr("width", inner.w + margin.left).attr("y", (d) => y(d)).attr("height", rowH)
    .attr("fill", "transparent")
    .on("mousemove", (event, grp) => showTip(event, `<div class="t-title">${grp}</div>` +
      tipRow("Burned: before → after", `${pct(share(grp, "burned", "before"))} → ${pct(share(grp, "burned", "after"))}`, css("--burned")) +
      tipRow("Control: before → after", `${pct(share(grp, "control", "before"))} → ${pct(share(grp, "control", "after"))}`, css("--control"))))
    .on("mouseleave", hideTip);
}
const pct = d3.format(".1%");

/* ---------------------------------------------------------------- 6. latitude */

function renderLatitude() {
  const rows = forEpisode("fct_species_latitude_shift");
  const el = document.getElementById("chart-latitude");
  const shown = d3.sort(rows, (d) => -Math.abs(d.shift_km) / Math.max(d.shift_se_km, 0.1)).slice(0, 15)
    .sort((a, b) => b.shift_km - a.shift_km);
  if (!shown.length) {
    el.innerHTML = `<p class="empty">No species has at least 30 observations both before and after.</p>`;
    return;
  }
  const narrow = el.clientWidth < 520;
  const rowH = 24;
  const margin = { top: 24, right: 20, bottom: 8, left: narrow ? 130 : 200 };
  const { g, inner } = svgFor("chart-latitude", shown.length * rowH + 32, margin);
  const ext = d3.max(shown, (d) => Math.abs(d.shift_km) + 2 * d.shift_se_km) || 1;
  const x = d3.scaleLinear().domain([-ext, ext]).nice().range([0, inner.w]);
  const y = d3.scaleBand().domain(shown.map((d) => d.species_key)).range([0, shown.length * rowH]);

  g.append("g").attr("class", "grid").selectAll("line").data(x.ticks(narrow ? 4 : 6)).join("line")
    .attr("x1", x).attr("x2", x).attr("y1", -4).attr("y2", shown.length * rowH);
  g.selectAll("text.tick").data(x.ticks(narrow ? 4 : 6)).join("text").attr("class", "tick")
    .attr("x", x).attr("y", -10).attr("text-anchor", "middle")
    .text((t) => (t === 0 ? "0 km" : `${t > 0 ? "N " : "S "}${Math.abs(t)}`));
  g.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", -4).attr("y2", shown.length * rowH).attr("stroke", "var(--axis)");

  const cy = (d) => y(d.species_key) + rowH / 2;
  g.selectAll("line.whisker").data(shown).join("line").attr("class", "whisker")
    .attr("x1", (d) => x(d.shift_km - 2 * d.shift_se_km)).attr("x2", (d) => x(d.shift_km + 2 * d.shift_se_km))
    .attr("y1", cy).attr("y2", cy).attr("stroke", "var(--neutral-mark-2)").attr("stroke-width", 2).attr("stroke-linecap", "round");
  g.selectAll("circle.dot").data(shown).join("circle").attr("class", "dot")
    .attr("cx", (d) => x(d.shift_km)).attr("cy", cy).attr("r", 5)
    .attr("fill", (d) => (d.is_notable ? "var(--neutral-mark)" : "var(--surface)"))
    .attr("stroke", (d) => (d.is_notable ? "var(--surface)" : "var(--neutral-mark)")).attr("stroke-width", 2);
  g.selectAll("text.name").data(shown).join("text").attr("class", "name label-mid")
    .attr("x", -10).attr("y", (d) => cy(d) + 4).attr("text-anchor", "end")
    .style("font-style", (d) => (d.species_name.startsWith("Demo") ? "normal" : "italic"))
    .text((d) => truncate(d.species_name, narrow ? 18 : 28));
  g.selectAll("rect.hit").data(shown).join("rect").attr("class", "hit")
    .attr("x", -margin.left).attr("width", inner.w + margin.left).attr("y", (d) => y(d.species_key)).attr("height", rowH)
    .attr("fill", "transparent")
    .on("mousemove", (event, d) => showTip(event, `<div class="t-title">${d.species_name}</div>` +
      tipRow("Shift", `${d.shift_km > 0 ? "+" : ""}${d.shift_km} km ${d.shift_km >= 0 ? "north" : "south"}`) +
      tipRow("± 2 standard errors", `${(2 * d.shift_se_km).toFixed(1)} km`) +
      tipRow("Observations before / after", `${fmt(d.n_before)} / ${fmt(d.n_after)}`)))
    .on("mouseleave", hideTip);
}

init().catch((err) => {
  console.error(err);
  document.querySelector("main").insertAdjacentHTML("afterbegin",
    `<p class="empty">Could not load data/*.json. Serve the folder over HTTP (python -m http.server) rather than opening the file directly.</p>`);
});
