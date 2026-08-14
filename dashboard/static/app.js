const state = {
  selectedItemKey: null,
  marketSort: "sales",
  moverDirection: "gainers",
};

const $ = (id) => document.getElementById(id);

function fmtNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtMoney(value) {
  if (value === null || value === undefined) return "-";
  const n = Number(value);
  if (Math.abs(n) >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${fmtNumber(n, 2)}`;
}

function itemLabel(row) {
  return row.display_name || (row.item_id || "Unknown").split(":").pop().replaceAll("_", " ");
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderMetrics(summary) {
  const latest = summary.latest_sale ? new Date(summary.latest_sale).toLocaleTimeString() : "-";
  $("metrics").innerHTML = [
    ["Sales", fmtNumber(summary.sales)],
    ["Listing Rows", fmtNumber(summary.listings)],
    ["Tracked Items", fmtNumber(summary.items)],
    ["1m Candles", fmtNumber(summary.candles)],
    ["Latest Sale", latest],
  ].map(([label, value]) => `
    <div class="metric">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
    </div>
  `).join("");
}

function renderMarkets(rows) {
  $("markets").innerHTML = rows.map((row) => `
    <tr data-item-key="${row.item_key}">
      <td>
        <div class="item-name">${itemLabel(row)}</div>
        <div class="item-id">${row.item_id}</div>
      </td>
      <td>${fmtMoney(row.sold_median_24h)}</td>
      <td>${fmtNumber(row.sales_count_24h)}</td>
      <td>${fmtNumber(row.units_sold_24h)}</td>
      <td>${fmtMoney(row.volume_24h)}</td>
      <td>${fmtMoney(row.lowest_listing)}</td>
    </tr>
  `).join("");

  $("markets").querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => selectItem(tr.dataset.itemKey));
  });

  if (!state.selectedItemKey && rows[0]) {
    selectItem(rows[0].item_key);
  }
}

function renderOpportunities(rows) {
  $("opportunities").innerHTML = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        <div class="item-name">${itemLabel(row)}</div>
        <div class="item-id">${fmtMoney(row.lowest_listing)} vs ${fmtMoney(row.market_value)}</div>
      </div>
      <div class="gain">${fmtNumber(row.discount_pct, 1)}%</div>
    </div>
  `).join("");
  $("opportunities").querySelectorAll(".list-row").forEach((row) => {
    row.addEventListener("click", () => selectItem(row.dataset.itemKey));
  });
}

function renderMovers(rows) {
  $("movers").innerHTML = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        <div class="item-name">${itemLabel(row)}</div>
        <div class="item-id">24h ${fmtMoney(row.sold_median_24h)} / 7d ${fmtMoney(row.sold_median_7d)}</div>
      </div>
      <div class="${row.change_pct >= 0 ? "gain" : "loss"}">${fmtNumber(row.change_pct, 1)}%</div>
    </div>
  `).join("");
  $("movers").querySelectorAll(".list-row").forEach((row) => {
    row.addEventListener("click", () => selectItem(row.dataset.itemKey));
  });
}

function drawChart(candles) {
  const canvas = $("chart");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#111512";
  ctx.fillRect(0, 0, rect.width, rect.height);

  const prices = candles.map((c) => c.vwap || c.median || c.close).filter((v) => v !== null);
  if (!prices.length) {
    ctx.fillStyle = "#9daaa1";
    ctx.fillText("No candles yet", 16, 28);
    return;
  }

  const pad = { left: 54, right: 18, top: 18, bottom: 32 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;

  ctx.strokeStyle = "#26302a";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (height * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(rect.width - pad.right, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#66a7ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  prices.forEach((price, index) => {
    const x = pad.left + (width * index) / Math.max(1, prices.length - 1);
    const y = pad.top + height - ((price - min) / span) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#9daaa1";
  ctx.font = "12px system-ui";
  ctx.fillText(fmtMoney(max), 10, pad.top + 5);
  ctx.fillText(fmtMoney(min), 10, rect.height - pad.bottom);

  const volumes = candles.map((c) => Number(c.units || 0));
  const maxVol = Math.max(...volumes, 1);
  ctx.fillStyle = "rgba(69, 212, 131, 0.28)";
  volumes.forEach((vol, index) => {
    const x = pad.left + (width * index) / Math.max(1, volumes.length - 1);
    const h = (vol / maxVol) * 44;
    ctx.fillRect(x, rect.height - pad.bottom - h, Math.max(1, width / volumes.length - 1), h);
  });
}

async function selectItem(itemKey) {
  state.selectedItemKey = itemKey;
  const item = await api(`/api/item?item_key=${encodeURIComponent(itemKey)}&limit=240`);
  $("chart-title").textContent = itemLabel(item);
  $("chart-meta").textContent = `${item.item_id} · 24h median ${fmtMoney(item.sold_median_24h)} · ${fmtNumber(item.sales_count_24h)} sales`;
  drawChart(item.candles || []);
}

async function refresh() {
  try {
    const [summary, markets, opps, movers] = await Promise.all([
      api("/api/summary"),
      api(`/api/markets?sort=${state.marketSort}&limit=30`),
      api("/api/opportunities?limit=12&min_sales=5"),
      api(`/api/movers?direction=${state.moverDirection}&limit=12`),
    ]);
    renderMetrics(summary);
    renderMarkets(markets);
    renderOpportunities(opps);
    renderMovers(movers);
    $("status").textContent = "Live";
  } catch (err) {
    $("status").textContent = "Error";
    console.error(err);
  }
}

document.querySelectorAll("[data-table='markets'] button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-table='markets'] button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.marketSort = button.dataset.sort;
    refresh();
  });
});

document.querySelectorAll("[data-table='movers'] button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-table='movers'] button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.moverDirection = button.dataset.direction;
    refresh();
  });
});

window.addEventListener("resize", () => {
  if (state.selectedItemKey) selectItem(state.selectedItemKey);
});

refresh();
setInterval(refresh, 15000);
