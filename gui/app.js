const state = {
  slots: [],
  configMeta: {},
  baseline: null,
  selected: new Set(),
  showBaseline: true,
  viewMode: "combined",
  globalMetric: "min",
  showServices: false,
  primaryMode: "latency",
  secondaryMode: "compliance",
  tertiaryMode: "tradeoff",
  filter5g: true,
  filterSat: true,
  filterSatPartial: true,
  playing: true,
  speed: 1,
  cursor: 0,
  live: true,
};

const historyLimit = 180;

const elements = {
  scenario: document.getElementById("context-scenario"),
  start: document.getElementById("context-start"),
  rel: document.getElementById("context-rel"),
  runtime: document.getElementById("context-runtime"),
  baseline: document.getElementById("context-baseline"),
  window: document.getElementById("context-window"),
  status5g: document.getElementById("status-5g"),
  statusSat: document.getElementById("status-sat"),
  group5g: document.getElementById("group-5g"),
  groupSat: document.getElementById("group-sat"),
  groupSatPartial: document.getElementById("group-sat-partial"),
  toggleBaseline: document.getElementById("toggle-baseline"),
  toggleExplainers: document.getElementById("toggle-explainers"),
  playToggle: document.getElementById("play-toggle"),
  speedSelect: document.getElementById("speed-select"),
  timeline: document.getElementById("timeline"),
  scoreboardTable: document.getElementById("scoreboard-table"),
  configExplain: document.getElementById("config-explain"),
  summaryTable: null,
  primary5g: document.getElementById("primary-5g"),
  primarySat: document.getElementById("primary-sat"),
  primary5gLegend: document.getElementById("primary-5g-legend"),
  primarySatLegend: document.getElementById("primary-sat-legend"),
  primary5gNote: document.getElementById("primary-5g-note"),
  primarySatNote: document.getElementById("primary-sat-note"),
  secondary5g: document.getElementById("secondary-5g"),
  secondarySat: document.getElementById("secondary-sat"),
  secondary5gLegend: document.getElementById("secondary-5g-legend"),
  secondarySatLegend: document.getElementById("secondary-sat-legend"),
  secondary5gServiceLegend: document.getElementById("secondary-5g-service-legend"),
  secondarySatServiceLegend: document.getElementById("secondary-sat-service-legend"),
  secondary5gNote: document.getElementById("secondary-5g-note"),
  secondarySatNote: document.getElementById("secondary-sat-note"),
  tradeoff: document.getElementById("tradeoff"),
  tradeoffLegend: document.getElementById("tradeoff-legend"),
  coverage: document.getElementById("coverage"),
  coverageLegend: document.getElementById("coverage-legend"),
  coverageNote: document.getElementById("coverage-note"),
  coverageBlock: document.getElementById("coverage-block"),
  primary5gBlock: document.getElementById("primary-5g-block"),
  primarySatBlock: document.getElementById("primary-sat-block"),
  secondary5gBlock: document.getElementById("secondary-5g-block"),
  secondarySatBlock: document.getElementById("secondary-sat-block"),
  primaryMode: document.getElementById("primary-mode"),
  secondaryMode: document.getElementById("secondary-mode"),
  tertiaryMode: document.getElementById("tertiary-mode"),
  tertiaryTitle: document.getElementById("tertiary-title"),
  primaryGrid: document.getElementById("primary-grid"),
  secondaryGrid: document.getElementById("secondary-grid"),
  tradeoffBlock: document.getElementById("tradeoff-block"),
  primaryTitle: document.getElementById("primary-title"),
  secondaryTitle: document.getElementById("secondary-title"),
};

const colors = [
  "#0b7a75",
  "#d17f58",
  "#4b5563",
  "#7c5fd3",
  "#2d6cdf",
  "#b84762",
];

const serviceColors = {
  etcs: "#2563eb",
  voice: "#f59e0b",
  video: "#10b981",
};

const satLevelColors = {
  SAT_TRANSPARENT: "#9ca3af",
  SAT_GW_EDGE: "#d17f58",
  SAT_ONBOARD: "#7c5fd3",
};

function ensureColorMap() {
  if (state.configOrder) return;
  state.configOrder = Object.keys(state.configMeta).sort();
}

function configColor(configId) {
  ensureColorMap();
  const idx = state.configOrder.indexOf(configId);
  const safeIndex = idx >= 0 ? idx : 0;
  return colors[safeIndex % colors.length];
}

function formatNumber(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function indexSlot(slot) {
  const map = new Map();
  slot.edge_results.forEach((item) => {
    if (!map.has(item.config_id)) {
      map.set(item.config_id, {});
    }
    map.get(item.config_id)[item.techno] = item;
  });
  slot._configMap = map;
}

function configLabel(configId) {
  const meta = state.configMeta[configId];
  if (!meta) return configId;
  return `${configId} — ${meta.ter} + ${meta.sat}`;
}

function getSlotAtCursor() {
  if (state.slots.length === 0) return null;
  const idx = Math.max(0, Math.min(state.cursor, state.slots.length - 1));
  return state.slots[idx];
}

function availableClass(flag) {
  return flag ? "status-pill active" : "status-pill";
}

function updateHeader(slot, info) {
  if (!slot) return;
  elements.scenario.textContent = slot.scenario || "—";
  elements.start.textContent = info?.config_used?.start_timestamp || "—";
  elements.rel.textContent = `${formatNumber(slot.t_rel_s, 1)}s`;
  elements.runtime.textContent = slot.t_runtime;
  elements.baseline.textContent = slot.baseline_config_id;

  elements.status5g.className = availableClass(slot.available_5g);
  elements.statusSat.className = availableClass(slot.available_sat);
  const ratio5g = slot.availability_ratio?.["5g"];
  const ratioSat = slot.availability_ratio?.["sat"];
  elements.status5g.textContent = `5G ${formatPercent(ratio5g)}`;
  elements.statusSat.textContent = `SAT ${formatPercent(ratioSat)}`;

  const baselineEntry = slot._configMap?.get(slot.baseline_config_id) || {};
  const fill5g = baselineEntry["5g"]?.window_fill_ratio;
  const fillSat = baselineEntry["sat"]?.window_fill_ratio;
  const fillValues = [fill5g, fillSat].filter((v) => v !== null && v !== undefined);
  const fill = fillValues.length ? Math.min(...fillValues) : 0;
  elements.window.textContent = formatPercent(fill);
}

function matchesFilter(meta, query) {
  if (!query) return true;
  const terms = query.toLowerCase().split(" ");
  return terms.every((term) => {
    if (term.startsWith("ter:")) {
      return meta.ter.toLowerCase().includes(term.slice(4));
    }
    if (term.startsWith("sat:")) {
      return meta.sat.toLowerCase().includes(term.slice(4));
    }
    return (
      meta.config_id.toLowerCase().includes(term) ||
      meta.ter.toLowerCase().includes(term) ||
      meta.sat.toLowerCase().includes(term)
    );
  });
}

function classifyConfig(meta) {
  if (!meta) return "unknown";
  if (meta.sat === "SAT_TRANSPARENT") return "5g";
  if (meta.sat_edge_fraction !== null && meta.sat_edge_fraction < 0.99) return "sat_partial";
  return "sat";
}

function updateSelectionFromFilters() {
  const selected = [];
  Object.values(state.configMeta).forEach((meta) => {
    const category = classifyConfig(meta);
    if (category === "5g" && state.filter5g) selected.push(meta.config_id);
    if (category === "sat" && state.filterSat) selected.push(meta.config_id);
    if (category === "sat_partial" && state.filterSatPartial) selected.push(meta.config_id);
  });
  const unique = Array.from(new Set(selected));
  unique.sort();
  state.selected = new Set(unique);
}

function renderConfigExplain() {
  if (!elements.configExplain) return;
  const configs = Object.values(state.configMeta);
  if (configs.length === 0) {
    elements.configExplain.innerHTML = "<h3>Configurations</h3><p>—</p>";
    return;
  }
  const lines = configs
    .map((meta) => {
      const frac = meta.sat_edge_fraction;
      const fracLabel = frac !== null && frac < 1 ? ` (sat ${Math.round(frac * 100)}%)` : "";
      return `<li><strong>${meta.config_id}</strong>: ${meta.ter} + ${meta.sat}${fracLabel}</li>`;
    })
    .join("");
  elements.configExplain.innerHTML = `
    <h3>Configurations</h3>
    <ul>${lines}</ul>
  `;
}

function setLegend(element, items) {
  if (!element) return;
  element.innerHTML = "";
  items.forEach((entry) => {
    const item = document.createElement("span");
    item.className = "legend-item";
    const dot = document.createElement("span");
    dot.className = "legend-dot";
    dot.style.background = entry.color;
    item.appendChild(dot);
    item.appendChild(document.createTextNode(entry.label));
    element.appendChild(item);
  });
}

function configLegendItems(configIds) {
  return configIds.map((configId) => ({
    label: configId,
    color: configColor(configId),
  }));
}

function getSelectedConfigs() {
  let selected = Array.from(state.selected).filter((id) => id !== state.baseline);
  selected.sort();
  if (state.showBaseline && state.baseline) {
    selected.unshift(state.baseline);
  }
  return selected;
}

function getTechList() {
  if (state.viewMode === "5g") return ["5g"];
  if (state.viewMode === "sat") return ["sat"];
  return ["5g", "sat"];
}

function getSeries(configId, tech, field) {
  const end = Math.max(0, Math.min(state.cursor, state.slots.length - 1));
  const start = Math.max(0, end - historyLimit + 1);
  const values = [];
  for (let i = start; i <= end; i += 1) {
    const slot = state.slots[i];
    const entry = slot._configMap?.get(configId)?.[tech];
    const value = entry ? resolveField(entry, field) : null;
    values.push(value === undefined ? null : value);
  }
  return values;
}

function getTimeSeries() {
  const end = Math.max(0, Math.min(state.cursor, state.slots.length - 1));
  const start = Math.max(0, end - historyLimit + 1);
  const values = [];
  for (let i = start; i <= end; i += 1) {
    values.push(state.slots[i]?.t_rel_s ?? null);
  }
  return values;
}

function resolveField(entry, field) {
  if (!field.includes(".")) return entry[field];
  return field.split(".").reduce((acc, key) => (acc ? acc[key] : null), entry);
}

function drawLineChart(canvas, series, options = {}) {
  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  const filtered = series.flatMap((item) =>
    item.values.filter((v) => v !== null && !Number.isNaN(v))
  );
  if (filtered.length === 0) return;
  const minVal = options.min ?? Math.min(...filtered);
  const maxVal = options.max ?? Math.max(...filtered);
  const span = Math.max(1e-3, maxVal - minVal);
  const padding = 36;
  const topPad = 10;

  ctx.strokeStyle = "#d4ccc0";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, topPad);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.font = "10px Space Grotesk";
  ctx.fillStyle = "#5f6b78";
  const ticks = 3;
  for (let i = 0; i <= ticks; i += 1) {
    const value = minVal + (i / ticks) * span;
    const y = height - padding - ((value - minVal) / span) * (height - padding - topPad);
    ctx.beginPath();
    ctx.moveTo(padding - 4, y);
    ctx.lineTo(padding, y);
    ctx.stroke();
    const label = `${value.toFixed(options.digits ?? 1)}${options.unit ?? ""}`;
    ctx.fillText(label, 2, y + 3);
  }

  const times = options.times || [];
  if (times.length > 1) {
    for (let i = 0; i <= 2; i += 1) {
      const idx = Math.round((i / 2) * (times.length - 1));
      const timeVal = times[idx];
      if (timeVal === null || timeVal === undefined) continue;
      const x = padding + (idx / Math.max(1, times.length - 1)) * (width - 2 * padding);
      ctx.beginPath();
      ctx.moveTo(x, height - padding);
      ctx.lineTo(x, height - padding + 4);
      ctx.stroke();
      const label = `${timeVal.toFixed(0)}${options.xUnit ?? "s"}`;
      ctx.fillText(label, x - 10, height - 4);
    }
    ctx.fillText(options.xLabel ?? "t_rel", width - 48, height - 4);
  }

  series.forEach((item) => {
    ctx.beginPath();
    ctx.strokeStyle = item.color;
    ctx.setLineDash(item.dash || []);
    ctx.lineWidth = 2;
    item.values.forEach((val, idx) => {
      if (val === null) return;
      const x = padding + (idx / Math.max(1, item.values.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - minVal) / span) * (height - padding - topPad);
      if (idx === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

function drawScatter(canvas, points) {
  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  if (points.length === 0) return;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(1e-3, maxX - minX);
  const spanY = Math.max(1e-3, maxY - minY);
  const padding = 32;
  const topPad = 10;

  ctx.strokeStyle = "#d4ccc0";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, topPad);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.font = "10px Space Grotesk";
  ctx.fillStyle = "#5f6b78";
  for (let i = 0; i <= 2; i += 1) {
    const value = minY + (i / 2) * spanY;
    const y = height - padding - ((value - minY) / spanY) * (height - padding - topPad);
    ctx.fillText(value.toFixed(1), 4, y + 3);
  }
  ctx.fillText("gain ms", 4, topPad + 6);

  for (let i = 0; i <= 2; i += 1) {
    const value = minX + (i / 2) * spanX;
    const x = padding + ((value - minX) / spanX) * (width - 2 * padding);
    ctx.fillText(value.toFixed(1), x - 8, height - 4);
  }
  ctx.fillText("compute ms", width - 70, height - 4);

  points.forEach((point) => {
    const x = padding + ((point.x - minX) / spanX) * (width - 2 * padding);
    const y = height - padding - ((point.y - minY) / spanY) * (height - padding - topPad);
    ctx.beginPath();
    ctx.fillStyle = point.color;
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
}

function drawCoverageChart(canvas, series) {
  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  const allY = series.flatMap((item) => item.points.map((point) => point.y));
  if (allY.length === 0) return;
  const minY = Math.min(...allY);
  const maxY = Math.max(...allY);
  const spanY = Math.max(1e-3, maxY - minY);
  const padding = 36;
  const topPad = 10;

  ctx.strokeStyle = "#d4ccc0";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, topPad);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.font = "10px Space Grotesk";
  ctx.fillStyle = "#5f6b78";
  for (let i = 0; i <= 2; i += 1) {
    const value = minY + (i / 2) * spanY;
    const y = height - padding - ((value - minY) / spanY) * (height - padding - topPad);
    ctx.fillText(value.toFixed(1), 2, y + 3);
  }
  for (let i = 0; i <= 2; i += 1) {
    const x = padding + (i / 2) * (width - 2 * padding);
    ctx.fillText(`${i * 50}%`, x - 10, height - 4);
  }
  ctx.fillText("coverage", width - 58, height - 4);
  ctx.fillText("latency ms", 2, topPad + 8);

  series.forEach((item) => {
    const points = item.points.sort((a, b) => a.x - b.x);
    ctx.beginPath();
    ctx.strokeStyle = item.color;
    ctx.lineWidth = 2;
    points.forEach((point, idx) => {
      const x = padding + point.x * (width - 2 * padding);
      const y = height - padding - ((point.y - minY) / spanY) * (height - padding - topPad);
      if (idx === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    points.forEach((point) => {
      const x = padding + point.x * (width - 2 * padding);
      const y = height - padding - ((point.y - minY) / spanY) * (height - padding - topPad);
      ctx.beginPath();
      ctx.fillStyle = item.color;
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
  });
}

function updateCharts() {
  const selected = getSelectedConfigs().slice(0, 4);
  const techs = getTechList();
  const times = getTimeSeries();

  const latencySeries = (tech) => {
    const series = [];
    selected.forEach((configId, idx) => {
      series.push({
        label: `${configId} edge`,
        color: configColor(configId),
        values: getSeries(configId, tech, "latency_edge_ms"),
      });
      if (state.showBaseline && configId === state.baseline) {
        series.push({
          label: `${configId} raw`,
          color: "#a2a9b0",
          dash: [4, 4],
          values: getSeries(configId, tech, "latency_raw_ms"),
        });
      }
    });
    return series;
  };

  const tailSeries = (tech) => {
    const series = [];
    selected.forEach((configId, idx) => {
      const baseColor = configColor(configId);
      series.push({
        label: `${configId} p50`,
        color: baseColor,
        dash: [],
        values: getSeries(configId, tech, "latency_p50_ms"),
      });
      series.push({
        label: `${configId} p95`,
        color: baseColor,
        dash: [6, 4],
        values: getSeries(configId, tech, "latency_p95_ms"),
      });
      series.push({
        label: `${configId} p99`,
        color: baseColor,
        dash: [2, 4],
        values: getSeries(configId, tech, "latency_p99_ms"),
      });
    });
    return series;
  };

  const complianceSeries = (tech) => {
    const series = [];
    selected.forEach((configId, idx) => {
      const metric = state.globalMetric === "min" ? "global_compliance" : "compliance_mean";
      series.push({
        label: `${configId} global`,
        color: configColor(configId),
        values: getSeries(configId, tech, metric),
      });
    });
    if (state.showServices) {
      const focus = state.baseline || selected[0];
      if (focus) {
        ["etcs", "voice", "video"].forEach((service) => {
          series.push({
            label: `${focus} ${service}`,
            color: serviceColors[service],
            dash: [4, 3],
            values: getSeries(focus, tech, `compliance.${service}`),
          });
        });
      }
    }
    return series;
  };

  const coreSeries = (tech) => {
    return selected.map((configId, idx) => ({
      label: `${configId} saved`,
      color: configColor(configId),
      values: getSeries(configId, tech, "core_traffic_saved_mbps"),
    }));
  };

  const drawPrimary = (tech) => {
    if (state.primaryMode === "latency") {
      drawLineChart(elements[tech === "5g" ? "primary5g" : "primarySat"], latencySeries(tech), {
        unit: " ms",
        digits: 1,
        times,
        xUnit: "s",
      });
      const note = state.showBaseline ? "baseline raw = dashed" : "";
      if (tech === "5g") elements.primary5gNote.textContent = note;
      if (tech === "sat") elements.primarySatNote.textContent = note;
    } else {
      drawLineChart(elements[tech === "5g" ? "primary5g" : "primarySat"], tailSeries(tech), {
        unit: " ms",
        digits: 1,
        times,
        xUnit: "s",
      });
      const note = "p50 solid · p95 dashed · p99 dotted";
      if (tech === "5g") elements.primary5gNote.textContent = note;
      if (tech === "sat") elements.primarySatNote.textContent = note;
    }
  };

  const drawSecondary = (tech) => {
    if (state.secondaryMode === "compliance") {
      drawLineChart(elements[tech === "5g" ? "secondary5g" : "secondarySat"], complianceSeries(tech), {
        min: 0,
        max: 1,
        digits: 2,
        times,
        xUnit: "s",
      });
      const focus = state.baseline || selected[0];
      if (tech === "5g") {
        elements.secondary5gNote.textContent = state.showServices && focus ? `services shown for ${focus}` : "";
      }
      if (tech === "sat") {
        elements.secondarySatNote.textContent = state.showServices && focus ? `services shown for ${focus}` : "";
      }
    } else if (state.secondaryMode === "core") {
      drawLineChart(elements[tech === "5g" ? "secondary5g" : "secondarySat"], coreSeries(tech), {
        unit: " Mbps",
        digits: 1,
        min: 0,
        times,
        xUnit: "s",
      });
      if (tech === "5g") elements.secondary5gNote.textContent = "";
      if (tech === "sat") elements.secondarySatNote.textContent = "";
    }
  };

  if (state.secondaryMode === "compliance" || state.secondaryMode === "core") {
    elements.secondaryGrid.style.display = "grid";
  }

  if (techs.includes("5g") && (state.secondaryMode === "compliance" || state.secondaryMode === "core")) {
    drawPrimary("5g");
    drawSecondary("5g");
    elements.primary5gBlock.style.display = "block";
    elements.secondary5gBlock.style.display = "block";
  } else {
    elements.primary5gBlock.style.display = "none";
    elements.secondary5gBlock.style.display = "none";
  }

  if (techs.includes("sat") && (state.secondaryMode === "compliance" || state.secondaryMode === "core")) {
    drawPrimary("sat");
    drawSecondary("sat");
    elements.primarySatBlock.style.display = "block";
    elements.secondarySatBlock.style.display = "block";
  } else {
    elements.primarySatBlock.style.display = "none";
    elements.secondarySatBlock.style.display = "none";
  }

  setLegend(elements.primary5gLegend, configLegendItems(selected));
  setLegend(elements.primarySatLegend, configLegendItems(selected));
  if (state.secondaryMode === "compliance" || state.secondaryMode === "core") {
    setLegend(elements.secondary5gLegend, configLegendItems(selected));
    setLegend(elements.secondarySatLegend, configLegendItems(selected));
  } else {
    setLegend(elements.secondary5gLegend, []);
    setLegend(elements.secondarySatLegend, []);
  }
  if (state.secondaryMode === "compliance" && state.showServices) {
    setLegend(elements.secondary5gServiceLegend, [
      { label: "ETCS", color: serviceColors.etcs },
      { label: "Voice", color: serviceColors.voice },
      { label: "Video", color: serviceColors.video },
    ]);
    setLegend(elements.secondarySatServiceLegend, [
      { label: "ETCS", color: serviceColors.etcs },
      { label: "Voice", color: serviceColors.voice },
      { label: "Video", color: serviceColors.video },
    ]);
  } else {
    setLegend(elements.secondary5gServiceLegend, []);
    setLegend(elements.secondarySatServiceLegend, []);
  }
}

function updateTradeoff(slot) {
  if (!slot) return;
  if (state.tertiaryMode !== "tradeoff") {
    elements.tradeoffBlock.style.display = "none";
    return;
  }
  elements.tradeoffBlock.style.display = "block";
  elements.coverageBlock.style.display = "none";
  const selected = getSelectedConfigs().slice(0, 4);
  const points = [];
  selected.forEach((configId, idx) => {
    const entry = slot._configMap?.get(configId) || {};
    ["5g", "sat"].forEach((tech) => {
      if (state.viewMode !== "combined" && state.viewMode !== tech) return;
      const item = entry[tech];
      if (!item || item.latency_gain_ms === null || item.compute_ms === null) return;
      points.push({
        x: item.compute_ms,
        y: item.latency_gain_ms,
        color: configColor(configId),
      });
    });
  });
  drawScatter(elements.tradeoff, points);
  setLegend(elements.tradeoffLegend, configLegendItems(selected));
  if (elements.tradeoffLegend) {
    const note = document.createElement("span");
    note.className = "legend-item";
    note.textContent = "X=compute ms, Y=latency gain ms";
    elements.tradeoffLegend.appendChild(note);
  }
}

function updateCoverage(slot) {
  if (!slot) return;
  if (state.tertiaryMode !== "coverage") {
    elements.coverageBlock.style.display = "none";
    return;
  }
  elements.coverageBlock.style.display = "block";
  elements.tradeoffBlock.style.display = "none";

  const selected = getSelectedConfigs();
  const grouped = {};
  const lastAvailable = (configId, field) => {
    for (let i = state.cursor; i >= 0; i -= 1) {
      const slotItem = state.slots[i]._configMap?.get(configId)?.sat;
      if (!slotItem) continue;
      const value = slotItem[field];
      if (value !== null && value !== undefined) return value;
    }
    return null;
  };

  selected.forEach((configId) => {
    const item = slot._configMap?.get(configId)?.sat;
    const meta = state.configMeta[configId];
    const coverage =
      item?.edge_fraction ??
      meta?.sat_edge_fraction ??
      (meta?.sat === "SAT_TRANSPARENT" ? 0.0 : 1.0);
    const p95 = item?.latency_p95_ms ?? lastAvailable(configId, "latency_p95_ms");
    const fallback = item?.latency_edge_ms ?? lastAvailable(configId, "latency_edge_ms");
    const latency = p95 ?? fallback;
    if (latency === null || latency === undefined) return;
    const level = item?.sat_level || meta?.sat || "SAT";
    if (!grouped[level]) grouped[level] = [];
    grouped[level].push({ x: coverage, y: latency });
  });

  const series = Object.keys(grouped).map((level) => {
    const points = grouped[level];
    const aggregated = {};
    points.forEach((point) => {
      const key = point.x.toFixed(2);
      if (!aggregated[key]) aggregated[key] = [];
      aggregated[key].push(point.y);
    });
    const averaged = Object.entries(aggregated).map(([key, values]) => ({
      x: Number(key),
      y: values.reduce((a, b) => a + b, 0) / values.length,
    }));
    return {
      label: level,
      color: satLevelColors[level] || "#6b7280",
      points: averaged,
    };
  });

  drawCoverageChart(elements.coverage, series);
  setLegend(
    elements.coverageLegend,
    series.map((item) => ({ label: item.label, color: item.color }))
  );
  const usesFallback = series.length > 0 && !slot.available_sat;
  elements.coverageNote.textContent = usesFallback
    ? "p95 latency vs coverage (last SAT sample)"
    : "p95 latency vs SAT coverage";
}

function renderScoreboard(slot) {
  if (!slot) return;
  const selected = getSelectedConfigs().slice(0, 10);
  elements.scoreboardTable.innerHTML = "";

  const header = document.createElement("div");
  header.className = "score-row header";
  header.innerHTML =
    "<div>Config</div><div>5G min/mean</div><div>SAT min/mean</div><div>5G gain</div><div>SAT gain</div><div>SAT edge</div><div>Core saved</div>";
  elements.scoreboardTable.appendChild(header);

  selected.forEach((configId) => {
    const entry = slot._configMap?.get(configId) || {};
    const row = document.createElement("div");
    row.className = `score-row${configId === state.baseline ? " baseline" : ""}`;
    const item5g = entry["5g"] || {};
    const itemSat = entry["sat"] || {};
    const meta = state.configMeta[configId];
    const label = meta ? `${meta.ter} + ${meta.sat}` : "";
    const global5g = state.globalMetric === "min" ? item5g.global_compliance : item5g.compliance_mean;
    const globalSat = state.globalMetric === "min" ? itemSat.global_compliance : itemSat.compliance_mean;
    const savedTotal = item5g.core_traffic_saved_mbps_total ?? itemSat.core_traffic_saved_mbps_total;
    const satEdge = itemSat.edge_fraction;
    const satDetour = itemSat.detour_ms;
    row.innerHTML = `
      <div>
        <strong>${configId}</strong>
        <div class="muted">${label}</div>
        <div>
          <span class="pill">5G ${item5g.available ? "OK" : "N/A"}</span>
          <span class="pill">SAT ${itemSat.available ? "OK" : "N/A"}</span>
        </div>
      </div>
      <div>${formatPercent(item5g.global_compliance)} / ${formatPercent(item5g.compliance_mean)}</div>
      <div>${formatPercent(itemSat.global_compliance)} / ${formatPercent(itemSat.compliance_mean)}</div>
      <div>${formatNumber(item5g.latency_gain_ms, 1)} ms</div>
      <div>${formatNumber(itemSat.latency_gain_ms, 1)} ms</div>
      <div>${formatPercent(satEdge)} · ${formatNumber(satDetour, 1)} ms</div>
      <div>${formatNumber(savedTotal, 2)} Mbps</div>
    `;
    elements.scoreboardTable.appendChild(row);
  });
}

function worstService(item) {
  const services = [
    ["ETCS", item.compliance?.etcs],
    ["Voice", item.compliance?.voice],
    ["Video", item.compliance?.video],
  ].filter((entry) => entry[1] !== null && entry[1] !== undefined);
  if (services.length === 0) return { label: "—", value: null };
  services.sort((a, b) => a[1] - b[1]);
  return { label: services[0][0], value: services[0][1] };
}

function updateTimelineSlider() {
  elements.timeline.max = Math.max(0, state.slots.length - 1);
  elements.timeline.value = state.cursor;
}

function handlePlayback() {
  if (!state.playing) return;
  if (state.live) {
    state.cursor = state.slots.length - 1;
    return;
  }
  const step = Math.max(1, Math.round(state.speed));
  state.cursor = Math.min(state.cursor + step, state.slots.length - 1);
  if (state.cursor === state.slots.length - 1) {
    state.live = true;
  }
}

async function fetchInfo() {
  const res = await fetch("/api/info");
  const data = await res.json();
  if (!data.ok) return null;
  if (data.payload?.config_used?.edge_configs) {
    state.configOrder = null;
    data.payload.config_used.edge_configs.forEach((cfg) => {
      state.configMeta[cfg.config_id] = {
        config_id: cfg.config_id,
        ter: cfg.ter,
        sat: cfg.sat,
        sat_edge_fraction: cfg.sat_edge_fraction ?? null,
      };
    });
  }
  updateSelectionFromFilters();
  renderConfigExplain();
  if (elements.toggleExplainers) {
    const panel = document.getElementById("explainers");
    panel.style.display = elements.toggleExplainers.checked ? "block" : "none";
  }
  return data.payload;
}

async function fetchSlots() {
  const res = await fetch(`/api/slots?limit=${historyLimit * 4}`);
  const data = await res.json();
  if (!data.ok) return;
  state.slots = data.payload || [];
  state.slots.forEach((slot) => indexSlot(slot));
  if (state.slots.length && Object.keys(state.configMeta).length === 0) {
    state.configOrder = null;
    const sample = state.slots[state.slots.length - 1];
    sample.edge_results.forEach((item) => {
      if (!state.configMeta[item.config_id]) {
        state.configMeta[item.config_id] = {
          config_id: item.config_id,
          ter: item.ter_level,
          sat: item.sat_level,
          sat_edge_fraction: item.edge_fraction ?? null,
        };
      }
    });
    updateSelectionFromFilters();
    renderConfigExplain();
  }
  if (state.slots.length) {
    state.baseline = state.slots[state.slots.length - 1].baseline_config_id;
    if (state.selected.size === 0) {
      Object.keys(state.configMeta).forEach((id) => state.selected.add(id));
    }
    state.cursor = state.slots.length - 1;
    updateTimelineSlider();
  }
}

async function pollLatest() {
  const res = await fetch("/api/latest");
  const data = await res.json();
  if (!data.ok || !data.payload) return;
  const latest = data.payload;
  const lastSlot = state.slots[state.slots.length - 1];
  if (!lastSlot || latest.t_rel_s > lastSlot.t_rel_s) {
    indexSlot(latest);
    state.slots.push(latest);
    if (Object.keys(state.configMeta).length === 0) {
      state.configOrder = null;
      latest.edge_results.forEach((item) => {
        if (!state.configMeta[item.config_id]) {
          state.configMeta[item.config_id] = {
            config_id: item.config_id,
            ter: item.ter_level,
            sat: item.sat_level,
            sat_edge_fraction: item.edge_fraction ?? null,
          };
        }
      });
      updateSelectionFromFilters();
      renderConfigExplain();
    }
    if (state.live) {
      state.cursor = state.slots.length - 1;
    }
    updateTimelineSlider();
  }
}

function render() {
  const slot = getSlotAtCursor();
  if (!slot) return;
  updateHeader(slot, state.info);
  renderScoreboard(slot);
  updateCharts();
  updateTradeoff(slot);
  updateCoverage(slot);
}

function setupControls() {
  elements.group5g.addEventListener("change", (event) => {
    state.filter5g = event.target.checked;
    updateSelectionFromFilters();
  });
  elements.groupSat.addEventListener("change", (event) => {
    state.filterSat = event.target.checked;
    updateSelectionFromFilters();
  });
  elements.groupSatPartial.addEventListener("change", (event) => {
    state.filterSatPartial = event.target.checked;
    updateSelectionFromFilters();
  });
  elements.toggleBaseline.addEventListener("change", (event) => {
    state.showBaseline = event.target.checked;
  });
  elements.toggleExplainers.addEventListener("change", (event) => {
    const panel = document.getElementById("explainers");
    panel.style.display = event.target.checked ? "block" : "none";
  });

  elements.primaryMode.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      elements.primaryMode.querySelectorAll("button").forEach((btn) => btn.classList.remove("active"));
      button.classList.add("active");
      state.primaryMode = button.dataset.mode;
      elements.primaryTitle.textContent = state.primaryMode === "latency" ? "Latency" : "Tail latency";
    });
  });

  elements.secondaryMode.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      elements.secondaryMode.querySelectorAll("button").forEach((btn) => btn.classList.remove("active"));
      button.classList.add("active");
      state.secondaryMode = button.dataset.mode;
      if (state.secondaryMode === "compliance") {
        elements.secondaryTitle.textContent = "Compliance";
      } else if (state.secondaryMode === "core") {
        elements.secondaryTitle.textContent = "Bandwidth saved";
      } else if (state.secondaryMode === "tradeoff") {
        elements.secondaryTitle.textContent = "Trade-off";
      } else {
        elements.secondaryTitle.textContent = "Sat coverage";
      }
    });
  });

  elements.tertiaryMode.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      elements.tertiaryMode.querySelectorAll("button").forEach((btn) => btn.classList.remove("active"));
      button.classList.add("active");
      state.tertiaryMode = button.dataset.mode;
      elements.tertiaryTitle.textContent = state.tertiaryMode === "coverage" ? "Sat coverage" : "Trade-off";
    });
  });

  document.querySelectorAll("input[name='tech-view']").forEach((radio) => {
    radio.addEventListener("change", (event) => {
      state.viewMode = event.target.value;
    });
  });

  document.querySelectorAll("input[name='global-metric']").forEach((radio) => {
    radio.addEventListener("change", (event) => {
      state.globalMetric = event.target.value;
    });
  });

  document.getElementById("toggle-services").addEventListener("change", (event) => {
    state.showServices = event.target.checked;
  });

  elements.playToggle.addEventListener("click", () => {
    state.playing = !state.playing;
    elements.playToggle.textContent = state.playing ? "Pause" : "Play";
  });

  elements.speedSelect.addEventListener("change", (event) => {
    state.speed = Number(event.target.value);
  });

  elements.timeline.addEventListener("input", (event) => {
    state.cursor = Number(event.target.value);
    state.live = state.cursor === state.slots.length - 1;
    render();
  });
}

async function init() {
  state.info = await fetchInfo();
  await fetchSlots();
  setupControls();
  render();

  setInterval(async () => {
    await pollLatest();
    handlePlayback();
    render();
  }, 1000);
}

window.addEventListener("resize", () => {
  render();
});

init();
