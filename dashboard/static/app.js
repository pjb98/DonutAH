const state = {
  selectedItemKey: null,
  marketSort: "sales",
  searchTimer: null,
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

function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${fmtNumber(n, 1)}%`;
}

function pctClass(value) {
  if (value === null || value === undefined) return "";
  return Number(value) >= 0 ? "gain" : "loss";
}

function itemLabel(row) {
  return row.display_name || (row.item_id || "Unknown").split(":").pop().replaceAll("_", " ");
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderPulse(summary) {
  const pulse = summary.last_24h || {};
  $("market-pulse").innerHTML = [
    ["Market Volume", fmtMoney(pulse.volume), pulse.volume_change_pct === null ? "Last 24h" : `${fmtPct(pulse.volume_change_pct)} vs previous 24h`, pctClass(pulse.volume_change_pct)],
    ["Units Sold", fmtNumber(pulse.units), "Last 24h", ""],
    ["Transactions", fmtNumber(pulse.transactions), "Last 24h", ""],
    ["Market Activity", pulse.activity || "-", `${fmtNumber(pulse.tx_per_minute, 1)} sales/min`, "activity"],
  ].map(([label, value, detail, klass]) => `
    <div class="metric">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      <div class="detail ${klass}">${detail}</div>
    </div>
  `).join("");

  const latest = summary.latest_sale ? new Date(summary.latest_sale).toLocaleTimeString() : "-";
  $("status-grid").innerHTML = [
    ["Total Sales", fmtNumber(summary.sales)],
    ["Listing Rows", fmtNumber(summary.listings)],
    ["Tracked Items", fmtNumber(summary.items)],
    ["1m Candles", fmtNumber(summary.candles)],
    ["Latest Sale", latest],
  ].map(([label, value]) => `
    <div>
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");
}

function variantBadge(row) {
  if (!row.variant_note) return "";
  return `<div class="variant-note">${row.variant_note}</div>`;
}

function renderMarkets(rows) {
  $("markets").innerHTML = rows.map((row) => `
    <tr data-item-key="${row.item_key}">
      <td>
        <div class="item-name">${itemLabel(row)}</div>
        <div class="item-id">${row.item_id}</div>
        ${variantBadge(row)}
      </td>
      <td>${fmtMoney(row.sold_median_24h || row.market_value)}</td>
      <td class="${pctClass(row.change_pct)}">${fmtPct(row.change_pct)}</td>
      <td>${fmtNumber(row.sales_count_24h)}</td>
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
        <div class="item-id">Ask ${fmtMoney(row.lowest_listing)} · Fair ${fmtMoney(row.market_value)}</div>
        ${variantBadge(row)}
      </div>
      <div class="gain">${fmtPct(row.discount_pct)}</div>
    </div>
  `).join("");
  $("opportunities").querySelectorAll(".list-row").forEach((row) => {
    row.addEventListener("click", () => selectItem(row.dataset.itemKey));
  });
}

function renderTrending(rows) {
  $("trending").innerHTML = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        <div class="item-name">${itemLabel(row)}</div>
        <div class="item-id">${fmtMoney(row.sold_median_24h)} · ${fmtNumber(row.sales_count_24h)} sales</div>
      </div>
      <div class="${pctClass(row.change_pct)}">${fmtPct(row.change_pct)}</div>
    </div>
  `).join("");
  $("trending").querySelectorAll(".list-row").forEach((row) => {
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
  ctx.fillStyle = "#101411";
  ctx.fillRect(0, 0, rect.width, rect.height);

  const prices = candles.map((c) => c.vwap || c.median || c.close).filter((v) => v !== null);
  if (!prices.length) {
    ctx.fillStyle = "#a5afa9";
    ctx.fillText("No candles yet", 16, 28);
    return;
  }

  const pad = { left: 58, right: 18, top: 18, bottom: 34 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;

  ctx.strokeStyle = "#28332d";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (height * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(rect.width - pad.right, y);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(pad.left, 0, rect.width - pad.right, 0);
  gradient.addColorStop(0, "#65a8ff");
  gradient.addColorStop(1, "#4ee08d");
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 2;
  ctx.beginPath();
  prices.forEach((price, index) => {
    const x = pad.left + (width * index) / Math.max(1, prices.length - 1);
    const y = pad.top + height - ((price - min) / span) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#a5afa9";
  ctx.font = "12px system-ui";
  ctx.fillText(fmtMoney(max), 10, pad.top + 5);
  ctx.fillText(fmtMoney(min), 10, rect.height - pad.bottom);

  const volumes = candles.map((c) => Number(c.units || 0));
  const maxVol = Math.max(...volumes, 1);
  ctx.fillStyle = "rgba(245, 189, 79, 0.25)";
  volumes.forEach((vol, index) => {
    const x = pad.left + (width * index) / Math.max(1, volumes.length - 1);
    const h = (vol / maxVol) * 42;
    ctx.fillRect(x, rect.height - pad.bottom - h, Math.max(1, width / volumes.length - 1), h);
  });
}

async function selectItem(itemKey) {
  state.selectedItemKey = itemKey;
  const item = await api(`/api/item?item_key=${encodeURIComponent(itemKey)}&limit=240`);
  $("chart-title").textContent = itemLabel(item);
  $("chart-meta").textContent = `${fmtMoney(item.sold_median_24h || item.market_value)} · ${fmtPct(item.change_pct)} 24h vs 7d · ${fmtNumber(item.sales_count_24h)} sales · ${fmtMoney(item.volume_24h)} volume`;
  $("item-badges").innerHTML = [
    item.lowest_listing ? `<span>Ask ${fmtMoney(item.lowest_listing)}</span>` : "",
    item.variant_note ? `<span>${item.variant_note}</span>` : "",
  ].join("");
  drawChart(item.candles || []);
}

async function runSearch(query) {
  const box = $("search-results");
  if (!query.trim()) {
    box.innerHTML = "";
    box.classList.remove("open");
    return;
  }
  const results = await api(`/api/search?q=${encodeURIComponent(query)}&limit=10`);
  box.innerHTML = results.map((row) => `
    <button class="search-result" data-item-key="${row.item_key}">
      <span>
        <strong>${itemLabel(row)}</strong>
        <small>${row.item_id}</small>
      </span>
      <span>${fmtMoney(row.sold_median_24h || row.lowest_listing)}</span>
    </button>
  `).join("");
  box.classList.toggle("open", results.length > 0);
  box.querySelectorAll(".search-result").forEach((button) => {
    button.addEventListener("click", () => {
      $("search").value = itemLabel(results.find((row) => row.item_key === button.dataset.itemKey));
      box.classList.remove("open");
      selectItem(button.dataset.itemKey);
    });
  });
}

async function refresh() {
  try {
    const markets = await api(`/api/markets?sort=${state.marketSort}&limit=35`);
    renderMarkets(markets);
    $("status").textContent = "Live";
  } catch (err) {
    $("status").textContent = "Error";
    console.error(err);
  }
}

async function refreshSecondary() {
  const tasks = [
    api("/api/summary").then(renderPulse),
    api("/api/opportunities?limit=12&min_sales=5").then(renderOpportunities),
    api("/api/markets?sort=gainers&limit=12").then(renderTrending),
  ];
  const results = await Promise.allSettled(tasks);
  if (results.some((result) => result.status === "rejected")) {
    $("status").textContent = "Partial";
    console.error(results.filter((result) => result.status === "rejected"));
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

$("search").addEventListener("input", (event) => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => runSearch(event.target.value), 160);
});

window.addEventListener("resize", () => {
  if (state.selectedItemKey) selectItem(state.selectedItemKey);
});

refresh();
refreshSecondary();
setInterval(refresh, 30000);
setInterval(refreshSecondary, 60000);
