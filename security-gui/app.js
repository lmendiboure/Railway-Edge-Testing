const state = {
  slots: [],
  historyLimit: 120,
  cursor: 0,
  live: true,
  info: null,
};

const elements = {
  scenarioName: document.getElementById("scenario-name"),
  attackState: document.getElementById("attack-state"),
  mitigationState: document.getElementById("mitigation-state"),
  slotTime: document.getElementById("slot-time"),
  attackType: document.getElementById("attack-type"),
  targetSegment: document.getElementById("target-segment"),
  attackIntensity: document.getElementById("attack-intensity"),
  metricsTable: document.getElementById("metrics-table"),
  latencyChart: document.getElementById("latency-chart"),
  jitterChart: document.getElementById("jitter-chart"),
  lossChart: document.getElementById("loss-chart"),
  throughputChart: document.getElementById("throughput-chart"),
  latencyLegend: document.getElementById("latency-legend"),
  throughputLegend: document.getElementById("throughput-legend"),
};

const colors = {
  baseline: "#9ca3af",
  impacted: "#b64c4c",
};

function formatNumber(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Number(value).toFixed(digits)}${suffix}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function getSlotAtCursor() {
  if (state.slots.length === 0) return null;
  const idx = Math.max(0, Math.min(state.cursor, state.slots.length - 1));
  return state.slots[idx];
}

function updateHeader(slot) {
  if (!slot) {
    elements.scenarioName.textContent = "—";
    elements.slotTime.textContent = "—";
    elements.attackType.textContent = "—";
    elements.targetSegment.textContent = "—";
    elements.attackIntensity.textContent = "—";
    elements.attackState.textContent = "Attack: —";
    elements.attackState.className = "pill";
    elements.mitigationState.textContent = "Mitigation: —";
    elements.mitigationState.className = "pill";
    return;
  }
  elements.scenarioName.textContent = slot.scenario || "—";
  elements.slotTime.textContent = slot.timestamp || "—";
  elements.attackType.textContent = slot.attack_type || "—";
  elements.targetSegment.textContent = slot.target_segment || "—";
  elements.attackIntensity.textContent = formatNumber(slot.attack_intensity, 2);

  const attackActive = slot.attack_active;
  elements.attackState.textContent = `Attack: ${attackActive ? "ACTIVE" : "INACTIVE"}`;
  elements.attackState.className = attackActive ? "pill active" : "pill";

  const mitigationActive = slot.mitigation_active;
  elements.mitigationState.textContent = `Mitigation: ${mitigationActive ? "ON" : "OFF"}`;
  elements.mitigationState.className = mitigationActive ? "pill ok" : "pill";
}

function renderMetricsTable(slot) {
  if (!elements.metricsTable) return;
  if (!slot) {
    elements.metricsTable.textContent = "Waiting for data...";
    return;
  }
  const baseline = slot.baseline || {};
  const impacted = slot.impacted || {};
  const rows = [
    { label: "Latency", key: "latency_ms", format: (v) => formatNumber(v, 1, " ms") },
    { label: "Jitter", key: "jitter_ms", format: (v) => formatNumber(v, 1, " ms") },
    { label: "Loss", key: "loss", format: (v) => formatPercent(v) },
    { label: "Throughput", key: "throughput_mbps", format: (v) => formatNumber(v, 2, " Mbps") },
    { label: "Compute", key: "compute_ms", format: (v) => formatNumber(v, 1, " ms") },
  ];
  elements.metricsTable.innerHTML = "";
  const header = document.createElement("div");
  header.className = "table-row header";
  header.innerHTML = "<span>Metric</span><span>Baseline</span><span>Impacted</span>";
  elements.metricsTable.appendChild(header);
  rows.forEach((row) => {
    const line = document.createElement("div");
    line.className = "table-row";
    line.innerHTML = `
      <span>${row.label}</span>
      <span>${row.format(baseline[row.key])}</span>
      <span>${row.format(impacted[row.key])}</span>
    `;
    elements.metricsTable.appendChild(line);
  });
}

function getSeries(field, source) {
  const end = state.slots.length;
  const start = Math.max(0, end - state.historyLimit);
  const values = [];
  for (let i = start; i < end; i += 1) {
    const slot = state.slots[i];
    const val = slot?.[source]?.[field];
    values.push(val === undefined ? null : val);
  }
  return values;
}

function getTimeSeries() {
  const end = state.slots.length;
  const start = Math.max(0, end - state.historyLimit);
  const values = [];
  for (let i = start; i < end; i += 1) {
    values.push(state.slots[i]?.t_rel_s ?? null);
  }
  return values;
}

function drawLineChart(canvas, series, options = {}) {
  const ctx = canvas.getContext("2d");
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width;
  canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  const filtered = series.flatMap((item) =>
    item.values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v))
  );
  if (filtered.length === 0) return;
  const minVal = options.min ?? Math.min(...filtered);
  const maxVal = options.max ?? Math.max(...filtered);
  const span = Math.max(1e-3, maxVal - minVal);
  const padding = 32;
  const topPad = 10;

  ctx.strokeStyle = "#d9d2c8";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding, topPad);
  ctx.lineTo(padding, height - padding);
  ctx.lineTo(width - padding, height - padding);
  ctx.stroke();

  ctx.font = "10px Space Grotesk";
  ctx.fillStyle = "#5b6470";
  for (let i = 0; i <= 2; i += 1) {
    const value = minVal + (i / 2) * span;
    const y = height - padding - ((value - minVal) / span) * (height - padding - topPad);
    ctx.fillText(value.toFixed(options.digits ?? 1), 2, y + 3);
  }

  const times = options.times || [];
  if (times.length > 1) {
    for (let i = 0; i <= 2; i += 1) {
      const idx = Math.round((i / 2) * (times.length - 1));
      const timeVal = times[idx];
      if (timeVal === null || timeVal === undefined) continue;
      const x = padding + (idx / Math.max(1, times.length - 1)) * (width - 2 * padding);
      ctx.fillText(`${timeVal.toFixed(0)}s`, x - 8, height - 4);
    }
  }

  series.forEach((item) => {
    ctx.beginPath();
    ctx.strokeStyle = item.color;
    ctx.lineWidth = 2;
    item.values.forEach((val, idx) => {
      if (val === null || val === undefined) return;
      const x = padding + (idx / Math.max(1, item.values.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - minVal) / span) * (height - padding - topPad);
      if (idx === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
  });
}

function setLegend(element) {
  if (!element) return;
  element.innerHTML = "";
  [
    { label: "baseline", color: colors.baseline },
    { label: "impacted", color: colors.impacted },
  ].forEach((entry) => {
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

function updateCharts() {
  const times = getTimeSeries();
  const baselineLatency = getSeries("latency_ms", "baseline");
  const impactedLatency = getSeries("latency_ms", "impacted");
  drawLineChart(
    elements.latencyChart,
    [
      { color: colors.baseline, values: baselineLatency },
      { color: colors.impacted, values: impactedLatency },
    ],
    { digits: 1, times }
  );

  const baselineJitter = getSeries("jitter_ms", "baseline");
  const impactedJitter = getSeries("jitter_ms", "impacted");
  drawLineChart(
    elements.jitterChart,
    [
      { color: colors.baseline, values: baselineJitter },
      { color: colors.impacted, values: impactedJitter },
    ],
    { digits: 1, times }
  );

  const baselineLoss = getSeries("loss", "baseline");
  const impactedLoss = getSeries("loss", "impacted");
  drawLineChart(
    elements.lossChart,
    [
      { color: colors.baseline, values: baselineLoss },
      { color: colors.impacted, values: impactedLoss },
    ],
    { digits: 2, times, min: 0, max: 1 }
  );

  const baselineThroughput = getSeries("throughput_mbps", "baseline");
  const impactedThroughput = getSeries("throughput_mbps", "impacted");
  drawLineChart(
    elements.throughputChart,
    [
      { color: colors.baseline, values: baselineThroughput },
      { color: colors.impacted, values: impactedThroughput },
    ],
    { digits: 1, times, min: 0 }
  );

  setLegend(elements.latencyLegend);
  setLegend(elements.throughputLegend);
}

async function fetchInfo() {
  const res = await fetch("/api/info");
  const data = await res.json();
  if (!data.ok) return null;
  return data.payload;
}

async function fetchSlots() {
  const res = await fetch(`/api/slots?limit=${state.historyLimit * 4}`);
  const data = await res.json();
  if (!data.ok) return;
  state.slots = data.payload || [];
  if (state.slots.length) {
    state.cursor = state.slots.length - 1;
  }
}

async function pollLatest() {
  const res = await fetch("/api/latest");
  const data = await res.json();
  if (!data.ok || !data.payload) return;
  const latest = data.payload;
  const lastSlot = state.slots[state.slots.length - 1];
  if (lastSlot && latest.t_rel_s < lastSlot.t_rel_s) {
    state.slots = [];
    state.cursor = 0;
    state.live = true;
    state.info = await fetchInfo();
    await fetchSlots();
    return;
  }
  if (!lastSlot || latest.t_rel_s > lastSlot.t_rel_s) {
    state.slots.push(latest);
    if (state.live) {
      state.cursor = state.slots.length - 1;
    }
  }
}

function render() {
  const slot = getSlotAtCursor();
  updateHeader(slot);
  renderMetricsTable(slot);
  updateCharts();
}

async function init() {
  state.info = await fetchInfo();
  await fetchSlots();
  render();

  setInterval(async () => {
    if (state.slots.length === 0) {
      await fetchSlots();
    } else {
      await pollLatest();
    }
    render();
  }, 1000);
}

window.addEventListener("resize", () => {
  render();
});

init();
