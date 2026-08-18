const state = {
  selectedItemKey: null,
  marketSort: "sales",
  searchTimer: null,
  chartRange: "24h",
  chartMode: "price",
  chartPoints: [],
  currentCandles: [],
  currentItem: null,
  auth: null,
  villagerProfession: "all",
  villagerSort: "sales",
};

const $ = (id) => document.getElementById(id);

function fmtNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function fmtMoney(value) {
  if (value === null || value === undefined) return "-";
  const n = Number(value);
  const compact = (divisor, suffix) => {
    const scaled = n / divisor;
    const abs = Math.abs(scaled);
    const digits = abs >= 100 ? 0 : 2;
    return `$${fmtNumber(scaled, digits)}${suffix}`;
  };
  if (Math.abs(n) >= 1_000_000_000) return compact(1_000_000_000, "B");
  if (Math.abs(n) >= 1_000_000) return compact(1_000_000, "M");
  if (Math.abs(n) >= 1_000) return compact(1_000, "K");
  return `$${fmtNumber(Math.round(n))}`;
}

function fmtListing(value) {
  return value === null || value === undefined ? "No listings seen" : fmtMoney(value);
}

function plainPrice(value) {
  return value === null || value === undefined ? "unknown" : fmtMoney(value);
}

function timeAgo(ms) {
  if (!ms) return "-";
  const seconds = Math.max(0, Math.floor((Date.now() - Number(ms)) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function fmtDurationMs(value) {
  if (value === null || value === undefined) return "";
  const totalSeconds = Math.max(0, Math.floor(Number(value) / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days) return `${days}d ${hours}h left`;
  if (hours) return `${hours}h ${minutes}m left`;
  return `${minutes}m left`;
}

function fmtClock(ms) {
  if (!ms) return "-";
  return new Date(Number(ms)).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
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

function profitClass(value) {
  if (value === null || value === undefined) return "";
  return Number(value) > 0 ? "gain" : Number(value) < 0 ? "loss" : "";
}

function freshness(snapshotAt) {
  const seenAt = Date.parse(snapshotAt);
  if (!seenAt) return { klass: "old", label: "Last seen unknown" };
  const minutes = (Date.now() - seenAt) / 60000;
  if (minutes <= 5) return { klass: "fresh", label: `Seen ${timeAgo(seenAt)}` };
  if (minutes <= 20) return { klass: "recent", label: `Seen ${timeAgo(seenAt)}` };
  return { klass: "old", label: `Seen ${timeAgo(seenAt)}` };
}

function rollingValues(values, windowSize = 7) {
  return values.map((_, index) => {
    const start = Math.max(0, index - Math.floor(windowSize / 2));
    const end = Math.min(values.length, index + Math.ceil(windowSize / 2));
    const slice = values.slice(start, end).filter((value) => value !== null && value !== undefined);
    if (!slice.length) return null;
    return slice.reduce((sum, value) => sum + Number(value), 0) / slice.length;
  });
}

function candlePrice(candle) {
  return candle.median || candle.vwap || candle.close;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function itemLabel(row) {
  return row?.display_name || row?.name || (row?.item_id || "Unknown").split(":").pop().replaceAll("_", " ");
}

function itemId(row) {
  if (typeof row === "string") return row;
  return row?.item_id || row?.id || row?.item?.item_id || "";
}

function minecraftIconId(row) {
  const id = itemId(row).replace(/^minecraft:/, "");
  if (id) return id;
  return itemLabel(row).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function iconFallbackLabel(row) {
  const label = itemLabel(row).trim();
  return label ? label[0].toUpperCase() : "?";
}

function itemIcon(row, size = "") {
  const label = escapeHtml(itemLabel(row));
  const iconId = encodeURIComponent(minecraftIconId(row));
  const fallback = escapeHtml(iconFallbackLabel(row));
  return `
    <span class="item-icon ${size}" aria-label="${label} icon">
      <img src="https://mc-icons.com/thumbs/${iconId}.png" alt="" loading="lazy" decoding="async" onerror="this.remove(); this.parentElement.classList.add('missing-icon');">
      <span>${fallback}</span>
    </span>
  `;
}

function itemNameHtml(row, subtext = "", size = "") {
  return `
    <div class="item-cell">
      ${itemIcon(row, size)}
      <div>
        <div class="item-name">${escapeHtml(itemLabel(row))}</div>
        ${subtext ? `<div class="item-id">${subtext}</div>` : ""}
      </div>
    </div>
  `;
}

function itemSubtext(row) {
  if (row.variant_note) return row.variant_note;
  if (row.sales_count_24h !== undefined) return `${fmtNumber(row.sales_count_24h)} sales · ${fmtMoney(row.volume_24h)} spent`;
  return "";
}

function itemPath(itemKey) {
  return `/item/${encodeURIComponent(itemKey)}`;
}

function setRouteMode() {
  const path = window.location.pathname;
  document.body.classList.toggle("item-route", Boolean(currentPathItemKey()));
  document.body.classList.toggle("account-route", path === "/account");
  document.body.classList.toggle("villager-route", path === "/villagers");
  document.body.classList.toggle("trending-route", path === "/trending");
  document.body.classList.toggle("deals-route", path === "/deals");
  document.body.classList.toggle("crafting-route", path === "/crafting");
  document.body.classList.toggle("pro-route", path === "/pro");
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderPulse(summary) {
  const pulse = summary.last_24h || {};
  $("market-pulse").innerHTML = [
    ["Money Spent", fmtMoney(pulse.volume), pulse.volume_change_pct === null ? "Last 24h" : `${fmtPct(pulse.volume_change_pct)} vs previous 24h`, pctClass(pulse.volume_change_pct)],
    ["Units Sold", fmtNumber(pulse.units), "Last 24h", ""],
    ["Sales", fmtNumber(pulse.transactions), "Last 24h", ""],
    ["How Busy", pulse.activity || "-", `${fmtNumber(pulse.tx_per_minute, 1)} sales/min`, "activity"],
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
        ${itemNameHtml(row, itemSubtext(row))}
      </td>
      <td>${fmtMoney(row.sold_median_24h || row.market_value)}</td>
      <td class="${pctClass(row.change_pct)}">${fmtPct(row.change_pct)}</td>
      <td>${fmtNumber(row.sales_count_24h)}</td>
      <td>${fmtMoney(row.volume_24h)}</td>
      <td>${fmtListing(row.lowest_listing)}</td>
    </tr>
  `).join("");

  $("markets").querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => navigateToItem(tr.dataset.itemKey));
  });

}

function renderOpportunities(rows) {
  const html = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        ${itemNameHtml(row, `Listed ${fmtMoney(row.lowest_listing)} · Usual ${fmtMoney(row.market_value)}`)}
        ${variantBadge(row)}
      </div>
      <div class="gain">${fmtPct(row.discount_pct)}</div>
    </div>
  `).join("");
  ["opportunities", "deals-page"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.innerHTML = html || `<div class="empty-note">No good buys found right now.</div>`;
    el.querySelectorAll(".list-row").forEach((row) => {
      row.addEventListener("click", () => navigateToItem(row.dataset.itemKey));
    });
  });
}

function renderTrending(rows) {
  const html = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        ${itemNameHtml(row, `${fmtMoney(row.sold_median_24h)} · ${fmtNumber(row.sales_count_24h)} sales`)}
      </div>
      <div class="${pctClass(row.change_pct)}">${fmtPct(row.change_pct)}</div>
    </div>
  `).join("");
  ["trending", "trending-page"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.innerHTML = html || `<div class="empty-note">No trending items found right now.</div>`;
    el.querySelectorAll(".list-row").forEach((row) => {
      row.addEventListener("click", () => navigateToItem(row.dataset.itemKey));
    });
  });
}

function drawChart(candles) {
  const canvas = $("chart");
  const tooltip = $("chart-tooltip");
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  state.currentCandles = candles;
  state.chartPoints = [];

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#101411";
  ctx.fillRect(0, 0, rect.width, rect.height);

  const mode = state.chartMode;
  const rawValues = candles.map((c) => {
    if (mode === "items") return Number(c.units || 0);
    if (mode === "money") return Number(c.volume || 0);
    return candlePrice(c);
  });
  const values = rawValues.filter((v) => v !== null && v !== undefined && !Number.isNaN(Number(v)));
  if (!values.length) {
    ctx.fillStyle = "#a5afa9";
    ctx.fillText("No candles yet", 16, 28);
    if (tooltip) tooltip.classList.remove("open");
    return;
  }

  const pad = { left: 66, right: 18, top: 24, bottom: 48 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const sorted = [...values].sort((a, b) => a - b);
  const lowIndex = mode === "price" ? Math.floor(sorted.length * 0.05) : 0;
  const highIndex = mode === "price" ? Math.max(lowIndex, Math.ceil(sorted.length * 0.95) - 1) : sorted.length - 1;
  let min = mode === "price" ? sorted[lowIndex] : 0;
  let max = sorted[highIndex];
  const excluded = mode === "price" ? values.filter((value) => value < min || value > max).length : 0;
  if (min === max) {
    min = Math.min(...values, 0);
    max = Math.max(...values, 1);
  }
  const span = max - min || 1;
  const chartValueLabel = mode === "items" ? "ITEMS SOLD" : mode === "money" ? "MONEY SPENT" : "PRICE";
  const formatChartValue = (value) => mode === "items" ? fmtNumber(value) : fmtMoney(value);
  const pointFor = (value, index) => {
    const x = pad.left + (width * index) / Math.max(1, candles.length - 1);
    const clamped = Math.max(min, Math.min(max, Number(value)));
    const y = pad.top + height - ((clamped - min) / span) * height;
    return { x, y };
  };

  ctx.strokeStyle = "#28332d";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (height * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(rect.width - pad.right, y);
    ctx.stroke();
  }

  if (mode === "price") {
    ctx.fillStyle = "rgba(165, 175, 169, 0.18)";
    candles.forEach((candle, index) => {
      [candle.low, candle.high].forEach((raw) => {
        if (raw === null || raw === undefined) return;
        const point = pointFor(raw, index);
        ctx.beginPath();
        ctx.arc(point.x, point.y, 2, 0, Math.PI * 2);
        ctx.fill();
      });
    });
  }

  const lineValues = mode === "price" ? rollingValues(rawValues, 9) : rawValues;
  const gradient = ctx.createLinearGradient(pad.left, 0, rect.width - pad.right, 0);
  gradient.addColorStop(0, "#65a8ff");
  gradient.addColorStop(1, "#4ee08d");
  ctx.strokeStyle = gradient;
  ctx.lineWidth = mode === "price" ? 3 : 2;
  ctx.beginPath();
  let hasLine = false;
  lineValues.forEach((value, index) => {
    if (value === null || value === undefined) return;
    const point = pointFor(value, index);
    if (!hasLine) ctx.moveTo(point.x, point.y);
    else ctx.lineTo(point.x, point.y);
    hasLine = true;
  });
  if (hasLine) ctx.stroke();

  ctx.fillStyle = "#a5afa9";
  ctx.font = "12px system-ui";
  ctx.fillText(chartValueLabel, pad.left, pad.top - 8);
  ctx.fillText(formatChartValue(max), 10, pad.top + 5);
  ctx.fillText(formatChartValue(min), 10, rect.height - pad.bottom);
  if (excluded) {
    ctx.fillStyle = "#f2bd55";
    ctx.fillText(`${excluded} unusual points clipped`, pad.left, pad.top + 16);
  }

  const volumes = candles.map((c) => Number(c.units || 0));
  const maxVol = Math.max(...volumes, 1);
  ctx.fillStyle = "#a5afa9";
  ctx.fillText("ITEMS SOLD", pad.left, rect.height - 8);
  ctx.fillStyle = mode === "items" ? "rgba(245, 189, 79, 0.45)" : "rgba(245, 189, 79, 0.22)";
  volumes.forEach((vol, index) => {
    const x = pad.left + (width * index) / Math.max(1, volumes.length - 1);
    const h = (vol / maxVol) * 52;
    ctx.fillRect(x, rect.height - pad.bottom - h, Math.max(1, width / volumes.length - 1), h);
  });

  state.chartPoints = candles.map((candle, index) => {
    const value = rawValues[index];
    const point = pointFor(value ?? 0, index);
    return { ...point, candle, value };
  });
}

function renderItemDetails(item) {
  state.currentItem = item;
  $("breadcrumbs").innerHTML = `<a href="/">Market</a><span>›</span><span>${escapeHtml(itemLabel(item))}</span>`;
  $("detail-title").innerHTML = `${itemIcon(item, "large")}<span>${escapeHtml(itemLabel(item))}</span>`;
  $("detail-subtitle").textContent = item.uses?.summary || "Live market data from recent DonutSMP auction sales.";
  $("detail-item-id").textContent = "";
  const marketPrice = item.price_each || item.market_value || item.sold_median_24h;
  const stackSize = item.max_stack || 64;
  $("market-price").textContent = fmtMoney(marketPrice);
  $("stack-price").innerHTML = [
    item.price_stack ? `≈ ${fmtMoney(item.price_stack)} per stack (${fmtNumber(stackSize)})` : "",
    `<span class="metric-help">Based on what players actually bought recently.</span>`,
  ].filter(Boolean).join("");
  $("movement-line").innerHTML = `<span class="${pctClass(item.change_pct)}">${fmtPct(item.change_pct)} 24h vs 7d</span>`;
  const suggested = item.suggested_prices || {};
  $("suggested-price").textContent = fmtMoney(suggested.market);
  $("suggested-stack").textContent = suggested.market && stackSize ? `${fmtMoney(suggested.market * stackSize)} / stack` : "";
  $("suggested-modes").innerHTML = [
    ["Sell Fast", suggested.quick],
    ["Normal", suggested.market],
    ["Try Higher", suggested.max_profit],
  ].map(([label, value]) => `
    <span>
      <strong>${label}</strong>
      <b>${fmtMoney(value)} each</b>
      <small>${value && stackSize ? `${fmtMoney(value * stackSize)} / stack` : "-"}</small>
    </span>
  `).join("");
  $("donut-says").innerHTML = `
    <strong>DonutDex Says</strong>
    <span>${itemLabel(item)} usually sells for around ${plainPrice(marketPrice)} each.</span>
    <span>The cheapest one seen right now is ${fmtListing(item.lowest_listing)}.</span>
    <span>Want to sell quickly? Try around ${plainPrice(suggested.quick)}.</span>
    <span>${fmtNumber(item.sales_count_24h)} ${itemLabel(item)} sales were recorded today.</span>
  `;

  $("detail-metrics").innerHTML = [
    ["Usual Price", fmtMoney(item.sold_median_24h)],
    ["Cheapest Now", fmtListing(item.lowest_listing)],
    ["Times Sold Today", fmtNumber(item.sales_count_24h)],
    ["Listings Now", fmtNumber(item.listing_count)],
    ["Amount Listed", fmtNumber(item.listed_quantity)],
    ["Money Spent Today", fmtMoney(item.volume_24h)],
  ].map(([label, value]) => `
    <div>
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");

  const advanced = [
    ["1h Price", fmtMoney(item.sold_median_1h)],
    ["7d Price", fmtMoney(item.sold_median_7d)],
    ["Price Change", fmtPct(item.change_pct)],
    ["Units Sold Today", fmtNumber(item.units_sold_24h)],
    ["Price Score", fmtNumber(item.liquidity_score, 0)],
    ["Average Listing", fmtMoney(item.median_listing), "Based on items currently listed for sale."],
  ];
  $("advanced-stats").innerHTML = advanced.map(([label, value, help]) => `
    <div>
      <span>${label}</span>
      <strong>${value}</strong>
      ${help ? `<small>${help}</small>` : ""}
    </div>
  `).join("");

  const crafts = item.uses?.crafting || [];
  renderCraftingUses(crafts, 0);

  $("recent-sales").innerHTML = (item.recent_sales || []).length ? `
    <div class="sales-table">
      <div class="sales-head"><span>Amount</span><span>Each</span><span>Total</span><span>Sold</span></div>
      ${item.recent_sales.map((sale) => `
        <div class="sales-row">
          <span>${itemIcon(item, "tiny")}${fmtNumber(sale.quantity)}</span>
          <strong>${fmtMoney(sale.price_each)}</strong>
          <strong>${fmtMoney(sale.total_price)}</strong>
          <span>${timeAgo(sale.sold_at_ms)}</span>
        </div>
      `).join("")}
    </div>
  ` : `<div class="empty-note">No recent sales captured.</div>`;

  renderListings(item);
}

function groupedListings(listings) {
  const groups = new Map();
  listings.forEach((listing) => {
    const enchantSummary = listing.enchant_summary || "Plain";
    const key = `${Number(listing.price_each || 0).toFixed(2)}|${enchantSummary}`;
    const current = groups.get(key) || {
      price_each: Number(listing.price_each || 0),
      enchant_summary: enchantSummary,
      quantity: 0,
      total_price: 0,
      count: 0,
      snapshot_at: listing.snapshot_at,
      time_left: listing.time_left,
    };
    current.quantity += Number(listing.quantity || 0);
    current.total_price += Number(listing.total_price || 0);
    current.count += 1;
    if (Date.parse(listing.snapshot_at) > Date.parse(current.snapshot_at || 0)) current.snapshot_at = listing.snapshot_at;
    if (listing.time_left !== null && listing.time_left !== undefined) {
      current.time_left = current.time_left === null || current.time_left === undefined
        ? listing.time_left
        : Math.min(current.time_left, listing.time_left);
    }
    groups.set(key, current);
  });
  return [...groups.values()].sort((a, b) => a.price_each - b.price_each);
}

function renderListings(item) {
  const listings = item.current_listings || [];
  if (!listings.length) {
    $("listing-depth").innerHTML = "";
    $("current-listings").innerHTML = `<div class="empty-note">No listings seen${item.listing_observed_at ? ` in latest scan` : ""}.</div>`;
    return;
  }
  const groups = groupedListings(listings);
  const maxQuantity = Math.max(...groups.map((group) => group.quantity), 1);
  $("listing-depth").innerHTML = `
    <div class="depth-title">Price Levels</div>
    ${groups.slice(0, 8).map((group) => `
      <div class="depth-row">
        <span>${fmtMoney(group.price_each)}</span>
        <div><i style="width:${Math.max(6, (group.quantity / maxQuantity) * 100)}%"></i></div>
        <strong>${fmtNumber(group.quantity)} listed</strong>
      </div>
    `).join("")}
  `;
  $("current-listings").innerHTML = groups.slice(0, 12).map((group) => {
    const seen = freshness(group.snapshot_at);
    return `
      <div class="compact-row listing-row">
        <div class="item-cell">
          ${itemIcon(item, "tiny")}
          <div>
            <strong>${fmtMoney(group.price_each)} each × ${fmtNumber(group.quantity)}</strong>
            <span><b class="listing-trait">${group.enchant_summary}</b> · ${fmtMoney(group.total_price)} total · ${group.count} listing${group.count === 1 ? "" : "s"} · ${fmtDurationMs(group.time_left)} · <em class="freshness ${seen.klass}">${seen.label}</em></span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function renderVillagerOptions(professions) {
  const select = $("villager-profession");
  const current = select.value || state.villagerProfession;
  select.innerHTML = [
    `<option value="all">All Villagers</option>`,
    ...professions.map((profession) => `<option value="${escapeHtml(profession)}">${escapeHtml(profession)}</option>`),
  ].join("");
  select.value = professions.includes(current) ? current : "all";
}

function renderVillagerItems(payload) {
  renderVillagerOptions(payload.professions || []);
  const items = payload.items || [];
  $("villager-items").innerHTML = items.length ? items.map((row) => `
    <tr data-item-key="${row.item_key || ""}" class="${row.item_key ? "" : "disabled-row"}">
      <td>${itemNameHtml(row, row.sales_count_24h ? `${fmtNumber(row.sales_count_24h)} sold today` : "No recent sales seen")}</td>
      <td>
        <strong>${escapeHtml(row.profession)}</strong>
        <div class="item-id">${escapeHtml(row.level)}</div>
      </td>
      <td>${fmtMoney(row.price_each)}</td>
      <td>${row.price_stack ? `${fmtMoney(row.price_stack)} / stack (${fmtNumber(row.max_stack)})` : "-"}</td>
      <td>${fmtListing(row.lowest_listing)}</td>
      <td>${fmtNumber(row.sales_count_24h)}</td>
      <td>${fmtNumber(row.listed_quantity)} items · ${fmtNumber(row.listing_count)} listings</td>
    </tr>
  `).join("") : `<tr><td colspan="7"><div class="empty-note">No villager trade items found.</div></td></tr>`;
  $("villager-items").querySelectorAll("tr[data-item-key]").forEach((row) => {
    if (!row.dataset.itemKey) return;
    row.addEventListener("click", () => navigateToItem(row.dataset.itemKey));
  });
}

async function loadVillagers() {
  const payload = await api(`/api/villagers?profession=${encodeURIComponent(state.villagerProfession)}&sort=${encodeURIComponent(state.villagerSort)}`);
  renderVillagerItems(payload);
}

function recipeDetail(recipe) {
  const canPriceRecipe = recipe.profit !== null && recipe.profit !== undefined;
  const recipeStats = [
    recipe.result_value !== null && recipe.result_value !== undefined ? ["Sell For", fmtMoney(recipe.result_value)] : null,
    recipe.ingredient_cost !== null && recipe.ingredient_cost !== undefined ? ["Cost to Make", fmtMoney(recipe.ingredient_cost)] : null,
    recipe.result.sales_count_24h !== null && recipe.result.sales_count_24h !== undefined ? ["Times Sold Today", fmtNumber(recipe.result.sales_count_24h)] : null,
    recipe.result.volume_24h !== null && recipe.result.volume_24h !== undefined ? ["Money Spent Today", fmtMoney(recipe.result.volume_24h)] : null,
  ].filter(Boolean);
  return `
    <div class="recipe-card">
      <div class="recipe-head">
        <div class="item-cell">
          ${itemIcon(recipe.result)}
          <div>
            <strong>${escapeHtml(recipe.result.name)}</strong>
            <span>${fmtNumber(recipe.result.quantity || 1)} crafted${recipe.result.price_each ? ` · ${fmtMoney(recipe.result.price_each)} each` : ""}</span>
          </div>
        </div>
        <div class="recipe-profit ${profitClass(recipe.profit)}">
          ${canPriceRecipe ? fmtMoney(recipe.profit) : "Price unknown"}
          <span>${canPriceRecipe && recipe.profit_pct !== null && recipe.profit_pct !== undefined ? `${fmtPct(recipe.profit_pct)} extra money` : "Not enough sales to estimate"}</span>
        </div>
      </div>
      ${recipeStats.length ? `
        <div class="recipe-math">
          ${recipeStats.map(([label, value]) => `
            <div>
              <span>${label}</span>
              <strong>${value}</strong>
            </div>
          `).join("")}
        </div>
      ` : ""}
      <div class="ingredient-list">
        ${recipe.ingredients.map((ingredient) => `
          <div>
            <span class="item-cell">${itemIcon(ingredient, "tiny")}<span>${fmtNumber(ingredient.quantity)}x ${escapeHtml(ingredient.name)}</span></span>
            <strong>${fmtMoney(ingredient.total_cost)}</strong>
            <small>${fmtMoney(ingredient.price_each)} each</small>
          </div>
        `).join("")}
      </div>
      ${recipe.missing_prices?.length ? `<div class="empty-note">Not enough recent ${recipe.result.name} sales to estimate earnings.</div>` : ""}
    </div>
  `;
}

function renderCraftingUses(crafts, selectedIndex) {
  if (!crafts.length) {
    $("crafting-uses").innerHTML = `<div class="empty-note">No known crafting uses added yet.</div>`;
    return;
  }
  const active = Math.max(0, Math.min(selectedIndex, crafts.length - 1));
  $("crafting-uses").innerHTML = `
    <div class="craft-result-grid">
      ${crafts.map((recipe, index) => `
        <button class="craft-result ${index === active ? "active" : ""}" data-recipe-index="${index}">
          <strong class="item-cell">${itemIcon(recipe.result, "tiny")}<span>${escapeHtml(recipe.result.name)}</span></strong>
          <span>${recipe.profit === null || recipe.profit === undefined ? "Price unknown" : `${fmtMoney(recipe.profit)} extra`}</span>
          <span>${fmtNumber(recipe.result.sales_count_24h)} sold · ${fmtMoney(recipe.result.volume_24h)} spent</span>
        </button>
      `).join("")}
    </div>
    <div id="selected-recipe">${recipeDetail(crafts[active])}</div>
  `;
  $("crafting-uses").querySelectorAll("[data-recipe-index]").forEach((button) => {
    button.addEventListener("click", () => renderCraftingUses(crafts, Number(button.dataset.recipeIndex)));
  });
}

async function selectItem(itemKey, options = {}) {
  const settings = { updateUrl: true, scroll: true, ...options };
  state.selectedItemKey = itemKey;
  $("chart-title").textContent = "Loading item...";
  $("chart-meta").textContent = "";
  $("detail-title").textContent = "Loading item...";
  $("detail-subtitle").textContent = "";
  $("item-badges").innerHTML = "";
  if (settings.updateUrl && window.location.pathname !== itemPath(itemKey)) {
    history.pushState({ itemKey }, "", itemPath(itemKey));
  }
  setRouteMode();
  if (settings.scroll) {
    if (document.body.classList.contains("item-route")) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      $("item-detail-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  const item = await api(`/api/item?item_key=${encodeURIComponent(itemKey)}&range=${encodeURIComponent(state.chartRange)}`);
  $("chart-title").textContent = itemLabel(item);
  $("chart-meta").textContent = `${fmtMoney(item.sold_median_24h || item.market_value)} · ${fmtPct(item.change_pct)} 24h vs 7d · ${fmtNumber(item.sales_count_24h)} sold · ${fmtMoney(item.volume_24h)} spent`;
  $("item-badges").innerHTML = [
    `<span>${item.lowest_listing ? `Cheapest ${fmtMoney(item.lowest_listing)}` : "No listings seen"}</span>`,
    item.variant_note ? `<span>${item.variant_note}</span>` : "",
  ].join("");
  renderItemDetails(item);
  drawChart(item.candles || []);
}

function navigateToItem(itemKey) {
  selectItem(itemKey, { updateUrl: true, scroll: true });
}

function showChartTooltip(event) {
  const tooltip = $("chart-tooltip");
  const canvas = $("chart");
  if (!tooltip || !state.chartPoints.length) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const nearest = state.chartPoints.reduce((best, point) => (
    Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best
  ), state.chartPoints[0]);
  if (!nearest || Math.abs(nearest.x - x) > 28) {
    tooltip.classList.remove("open");
    return;
  }
  const candle = nearest.candle;
  const valueLabel = state.chartMode === "items" ? "Items sold" : state.chartMode === "money" ? "Money spent" : "Usual price";
  const value = state.chartMode === "items" ? fmtNumber(nearest.value) : fmtMoney(nearest.value);
  tooltip.innerHTML = `
    <strong>${fmtClock(candle.minute_ms)}</strong>
    <span>${valueLabel}: ${value}</span>
    <span>Sales: ${fmtNumber(candle.transactions)}</span>
    <span>Items: ${fmtNumber(candle.units)}</span>
    <span>Spent: ${fmtMoney(candle.volume)}</span>
  `;
  tooltip.style.left = `${Math.min(rect.width - 180, Math.max(8, nearest.x + 12))}px`;
  tooltip.style.top = `${Math.max(8, nearest.y - 48)}px`;
  tooltip.classList.add("open");
}

function hideChartTooltip() {
  $("chart-tooltip")?.classList.remove("open");
}

function currentPathItemKey() {
  if (!window.location.pathname.startsWith("/item/")) return "";
  return decodeURIComponent(window.location.pathname.slice("/item/".length));
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
      <span class="item-cell">
        ${itemIcon(row)}
        <span>
          <strong>${escapeHtml(itemLabel(row))}</strong>
          <small>${itemSubtext(row)}</small>
        </span>
      </span>
      <span>${fmtMoney(row.sold_median_24h || row.lowest_listing)}</span>
    </button>
  `).join("");
  box.classList.toggle("open", results.length > 0);
  box.querySelectorAll(".search-result").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = results.find((row) => row.item_key === button.dataset.itemKey);
      $("search").value = itemLabel(selected);
      box.classList.remove("open");
      navigateToItem(button.dataset.itemKey);
    });
  });
}

function authErrorMessage() {
  const params = new URLSearchParams(window.location.search);
  const error = params.get("auth_error");
  if (!error) return "";
  return error.replaceAll("_", " ");
}

function renderAccount(auth) {
  state.auth = auth;
  const user = auth.user;
  const message = authErrorMessage();
  $("auth-message").textContent = message ? `Login issue: ${message}` : "";
  $("login-card").style.display = user ? "none" : "block";
  $("profile-card").style.display = user ? "grid" : "none";
  $("account-history").style.display = user ? "block" : "none";
  $("login-buttons").innerHTML = auth.providers.map((provider) => `
    <a class="login-button ${provider.configured ? "" : "disabled"}" href="${provider.configured ? `/auth/${provider.provider}?next=/account` : "#"}" aria-disabled="${provider.configured ? "false" : "true"}">
      <strong>Continue with ${provider.label}</strong>
      <span>${provider.configured ? "Log in" : "Coming soon"}</span>
    </a>
  `).join("");
  if (!user) return;
  $("account-name").value = user.account_name || "";
  $("minecraft-name").value = user.minecraft_name || "";
  $("profile-subtitle").textContent = user.identities.length
    ? `Connected with ${user.identities.map((identity) => identity.provider).join(", ")}.`
    : "Connected account.";
  loadAccountTransactions();
}

async function loadAccount() {
  const auth = await api("/api/auth/me");
  renderAccount(auth);
}

async function saveProfile() {
  const res = await fetch("/api/account/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      account_name: $("account-name").value,
      minecraft_name: $("minecraft-name").value,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  const payload = await res.json();
  state.auth.user = payload.user;
  renderAccount(state.auth);
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST" });
  state.auth = null;
  await loadAccount();
}

async function loadAccountTransactions() {
  if (!state.auth?.user?.minecraft_name) {
    $("account-summary").innerHTML = `<div class="empty-note">Set your Minecraft name to see your sales.</div>`;
    $("account-sales").innerHTML = "";
    return;
  }
  const history = await api("/api/account/transactions?limit=100");
  const summary = history.summary || {};
  $("account-summary").innerHTML = `
    <div><span>Sales Found</span><strong>${fmtNumber(summary.sales || 0)}</strong></div>
    <div><span>Items Sold</span><strong>${fmtNumber(summary.items || 0)}</strong></div>
    <div><span>Money Earned</span><strong>${fmtMoney(summary.money || 0)}</strong></div>
  `;
  $("account-sales").innerHTML = history.sales.length ? `
    <div class="account-sales-head"><span>Item</span><span>Amount</span><span>Each</span><span>Total</span><span>Sold</span></div>
    ${history.sales.map((sale) => `
      <div class="account-sale-row">
        <span>${itemIcon(sale, "tiny")}${escapeHtml(itemLabel(sale))}</span>
        <span>${fmtNumber(sale.quantity)}</span>
        <strong>${fmtMoney(sale.price_each)}</strong>
        <strong>${fmtMoney(sale.total_price)}</strong>
        <span>${timeAgo(sale.sold_at_ms)}</span>
      </div>
    `).join("")}
  ` : `<div class="empty-note">No sales found for ${escapeHtml(state.auth.user.minecraft_name)} yet.</div>`;
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

window.addEventListener("popstate", () => {
  const itemKey = currentPathItemKey();
  setRouteMode();
  if (itemKey) {
    selectItem(itemKey, { updateUrl: false, scroll: true });
  } else if (window.location.pathname === "/account") {
    loadAccount();
  } else if (window.location.pathname === "/villagers") {
    loadVillagers();
  }
});

$("timeframes").querySelectorAll("button").forEach((button) => {
  button.addEventListener("click", () => {
    $("timeframes").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.chartRange = button.dataset.range;
    if (state.selectedItemKey) selectItem(state.selectedItemKey, { updateUrl: false, scroll: false });
  });
});

$("chart-modes").querySelectorAll("button").forEach((button) => {
  button.addEventListener("click", () => {
    $("chart-modes").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.chartMode = button.dataset.mode;
    drawChart(state.currentCandles || []);
  });
});

$("chart").addEventListener("mousemove", showChartTooltip);
$("chart").addEventListener("mouseleave", hideChartTooltip);

$("save-profile").addEventListener("click", () => {
  saveProfile().catch((err) => {
    $("auth-message").textContent = `Could not save profile: ${err.message}`;
  });
});

$("logout-button").addEventListener("click", () => {
  logout().catch((err) => {
    $("auth-message").textContent = `Could not log out: ${err.message}`;
  });
});

$("villager-profession").addEventListener("change", (event) => {
  state.villagerProfession = event.target.value;
  loadVillagers().catch(console.error);
});

$("villager-sort").querySelectorAll("button").forEach((button) => {
  button.addEventListener("click", () => {
    $("villager-sort").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.villagerSort = button.dataset.sort;
    loadVillagers().catch(console.error);
  });
});

$("search").addEventListener("input", (event) => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(() => runSearch(event.target.value), 160);
});

window.addEventListener("resize", () => {
  if (state.selectedItemKey) selectItem(state.selectedItemKey, { updateUrl: false, scroll: false });
});

setRouteMode();
refresh();
refreshSecondary();
const pathItemKey = currentPathItemKey();
if (pathItemKey) {
  selectItem(pathItemKey, { updateUrl: false, scroll: false });
}
if (window.location.pathname === "/account") {
  loadAccount();
}
if (window.location.pathname === "/villagers") {
  loadVillagers();
}
setInterval(refresh, 30000);
setInterval(refreshSecondary, 60000);
