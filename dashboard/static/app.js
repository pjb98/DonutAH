const state = {
  selectedItemKey: null,
  marketSort: "sales",
  searchTimer: null,
  chartRange: "24h",
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

function fmtAsk(value) {
  return value === null || value === undefined ? "No active asks" : fmtMoney(value);
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
  return row.display_name || (row.item_id || "Unknown").split(":").pop().replaceAll("_", " ");
}

function itemId(row) {
  if (typeof row === "string") return row;
  return row?.item_id || row?.id || row?.item?.item_id || "";
}

function iconData(row) {
  const id = itemId(row);
  const name = itemLabel(row).toLowerCase();
  const exact = {
    "minecraft:leather": ["🟫", "#7d4d30"],
    "minecraft:leather_helmet": ["🧢", "#7d4d30"],
    "minecraft:leather_chestplate": ["🧥", "#7d4d30"],
    "minecraft:leather_leggings": ["👖", "#7d4d30"],
    "minecraft:leather_boots": ["🥾", "#7d4d30"],
    "minecraft:diamond": ["💎", "#3ccfe0"],
    "minecraft:emerald": ["◆", "#21a854"],
    "minecraft:gold_ingot": ["▰", "#e0ad31"],
    "minecraft:iron_ingot": ["▰", "#c7c9c2"],
    "minecraft:netherite_ingot": ["▰", "#3b3234"],
    "minecraft:egg": ["🥚", "#e8dfc8"],
    "minecraft:paper": ["📄", "#dfd6ba"],
    "minecraft:item_frame": ["🖼️", "#a36b38"],
    "minecraft:stick": ["╱", "#8b5b2e"],
    "minecraft:string": ["⌁", "#d8d8d8"],
    "minecraft:obsidian": ["▣", "#221a34"],
    "minecraft:totem_of_undying": ["☥", "#d3a83e"],
    "minecraft:elytra": ["◢", "#6d7480"],
    "minecraft:spawner": ["▦", "#45545c"],
    "minecraft:dirt": ["▦", "#765039"],
    "minecraft:grass_block": ["▦", "#527c36"],
    "minecraft:oak_planks": ["▤", "#a2723a"],
    "minecraft:chest": ["▤", "#b5792e"],
    "minecraft:shulker_box": ["▣", "#b77dcc"],
    "minecraft:filled_map": ["▧", "#6a8a55"],
  };
  if (exact[id]) return exact[id];
  if (id.includes("diamond")) return ["◆", "#3ccfe0"];
  if (id.includes("emerald")) return ["◆", "#21a854"];
  if (id.includes("gold")) return ["▰", "#e0ad31"];
  if (id.includes("iron")) return ["▰", "#c7c9c2"];
  if (id.includes("netherite")) return ["▰", "#3b3234"];
  if (id.includes("leather")) return ["🟫", "#7d4d30"];
  if (id.includes("egg") || name.includes("egg")) return ["🥚", "#e8dfc8"];
  if (id.includes("sword")) return ["⚔", "#7e8790"];
  if (id.includes("pickaxe")) return ["⛏", "#7e8790"];
  if (id.includes("axe")) return ["🪓", "#7e8790"];
  if (id.includes("helmet")) return ["◠", "#7e8790"];
  if (id.includes("chestplate")) return ["▣", "#7e8790"];
  if (id.includes("leggings")) return ["▥", "#7e8790"];
  if (id.includes("boots")) return ["▴", "#7e8790"];
  if (id.includes("potion")) return ["⚗", "#9b6ee8"];
  if (id.includes("map")) return ["▧", "#6a8a55"];
  return ["▣", "#5f6f66"];
}

function itemIcon(row, size = "") {
  const [glyph, color] = iconData(row);
  const label = escapeHtml(itemLabel(row));
  return `<span class="item-icon ${size}" style="--icon-color:${color}" aria-label="${label} icon">${escapeHtml(glyph)}</span>`;
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
  if (row.sales_count_24h !== undefined) return `${fmtNumber(row.sales_count_24h)} sales · ${fmtMoney(row.volume_24h)} traded`;
  return "";
}

function itemPath(itemKey) {
  return `/item/${encodeURIComponent(itemKey)}`;
}

function setRouteMode() {
  document.body.classList.toggle("item-route", Boolean(currentPathItemKey()));
}

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function renderPulse(summary) {
  const pulse = summary.last_24h || {};
  $("market-pulse").innerHTML = [
    ["Money Traded", fmtMoney(pulse.volume), pulse.volume_change_pct === null ? "Last 24h" : `${fmtPct(pulse.volume_change_pct)} vs previous 24h`, pctClass(pulse.volume_change_pct)],
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
      <td>${fmtAsk(row.lowest_listing)}</td>
    </tr>
  `).join("");

  $("markets").querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => navigateToItem(tr.dataset.itemKey));
  });

  if (!state.selectedItemKey && rows[0] && !currentPathItemKey()) {
    selectItem(rows[0].item_key, { updateUrl: false, scroll: false });
  }
}

function renderOpportunities(rows) {
  $("opportunities").innerHTML = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        ${itemNameHtml(row, `Ask ${fmtMoney(row.lowest_listing)} · Fair ${fmtMoney(row.market_value)}`)}
        ${variantBadge(row)}
      </div>
      <div class="gain">${fmtPct(row.discount_pct)}</div>
    </div>
  `).join("");
  $("opportunities").querySelectorAll(".list-row").forEach((row) => {
    row.addEventListener("click", () => navigateToItem(row.dataset.itemKey));
  });
}

function renderTrending(rows) {
  $("trending").innerHTML = rows.map((row) => `
    <div class="list-row" data-item-key="${row.item_key}">
      <div>
        ${itemNameHtml(row, `${fmtMoney(row.sold_median_24h)} · ${fmtNumber(row.sales_count_24h)} sales`)}
      </div>
      <div class="${pctClass(row.change_pct)}">${fmtPct(row.change_pct)}</div>
    </div>
  `).join("");
  $("trending").querySelectorAll(".list-row").forEach((row) => {
    row.addEventListener("click", () => navigateToItem(row.dataset.itemKey));
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

  const prices = candles.map((c) => c.median || c.vwap || c.close).filter((v) => v !== null);
  if (!prices.length) {
    ctx.fillStyle = "#a5afa9";
    ctx.fillText("No candles yet", 16, 28);
    return;
  }

  const pad = { left: 58, right: 18, top: 18, bottom: 34 };
  const width = rect.width - pad.left - pad.right;
  const height = rect.height - pad.top - pad.bottom;
  const sorted = [...prices].sort((a, b) => a - b);
  const lowIndex = Math.floor(sorted.length * 0.05);
  const highIndex = Math.max(lowIndex, Math.ceil(sorted.length * 0.95) - 1);
  let min = sorted[lowIndex];
  let max = sorted[highIndex];
  const excluded = prices.filter((price) => price < min || price > max).length;
  if (min === max) {
    min = Math.min(...prices);
    max = Math.max(...prices);
  }
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
    const clamped = Math.max(min, Math.min(max, price));
    const y = pad.top + height - ((clamped - min) / span) * height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#a5afa9";
  ctx.font = "12px system-ui";
  ctx.fillText("PRICE", pad.left, pad.top - 4);
  ctx.fillText(fmtMoney(max), 10, pad.top + 5);
  ctx.fillText(fmtMoney(min), 10, rect.height - pad.bottom);
  if (excluded) {
    ctx.fillStyle = "#f2bd55";
    ctx.fillText(`${excluded} unusual points clipped`, pad.left, pad.top + 16);
  }

  const volumes = candles.map((c) => Number(c.units || 0));
  const maxVol = Math.max(...volumes, 1);
  ctx.fillStyle = "#a5afa9";
  ctx.fillText("ITEMS SOLD", pad.left, rect.height - 8);
  ctx.fillStyle = "rgba(245, 189, 79, 0.25)";
  volumes.forEach((vol, index) => {
    const x = pad.left + (width * index) / Math.max(1, volumes.length - 1);
    const h = (vol / maxVol) * 42;
    ctx.fillRect(x, rect.height - pad.bottom - h, Math.max(1, width / volumes.length - 1), h);
  });
}

function renderItemDetails(item) {
  $("detail-title").innerHTML = `${itemIcon(item, "large")}<span>${escapeHtml(itemLabel(item))}</span>`;
  $("detail-subtitle").textContent = item.uses?.summary || "Live market data from recent DonutSMP auction sales.";
  $("detail-item-id").textContent = "";
  const marketPrice = item.price_each || item.market_value || item.sold_median_24h;
  $("market-price").textContent = fmtMoney(marketPrice);
  $("stack-price").textContent = item.price_stack ? `≈ ${fmtMoney(item.price_stack)} per stack (${fmtNumber(item.max_stack || 64)})` : "";
  $("movement-line").innerHTML = `<span class="${pctClass(item.change_pct)}">${fmtPct(item.change_pct)} 24h vs 7d</span>`;
  const suggested = item.suggested_prices || {};
  $("suggested-price").textContent = fmtMoney(suggested.market);
  $("suggested-stack").textContent = suggested.market && item.max_stack ? `${fmtMoney(suggested.market * item.max_stack)} / stack` : "";
  $("suggested-modes").innerHTML = [
    ["Sell Fast", suggested.quick],
    ["Normal", suggested.market],
    ["Try Higher", suggested.max_profit],
  ].map(([label, value]) => `<span><strong>${label}</strong>${fmtMoney(value)}</span>`).join("");
  $("donut-says").innerHTML = `
    <strong>DonutDex Says</strong>
    <span>${itemLabel(item)} usually sells for around ${plainPrice(marketPrice)} each.</span>
    <span>The cheapest current listing is ${fmtAsk(item.lowest_listing)}.</span>
    <span>Want to sell quickly? Try around ${plainPrice(suggested.quick)}.</span>
    <span>${fmtNumber(item.sales_count_24h)} ${itemLabel(item)} sales were recorded today.</span>
  `;

  $("detail-metrics").innerHTML = [
    ["Typical Price", fmtMoney(item.sold_median_24h)],
    ["Cheapest Listing", fmtAsk(item.lowest_listing)],
    ["Sold Today", fmtNumber(item.sales_count_24h)],
    ["Listings Now", fmtNumber(item.listing_count)],
    ["Items Listed", fmtNumber(item.listed_quantity)],
    ["Money Traded Today", fmtMoney(item.volume_24h)],
  ].map(([label, value]) => `
    <div>
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `).join("");

  const crafts = item.uses?.crafting || [];
  renderCraftingUses(crafts, 0);

  $("recent-sales").innerHTML = (item.recent_sales || []).length ? item.recent_sales.map((sale) => `
    <div class="compact-row">
      <div class="item-cell">
        ${itemIcon(item, "tiny")}
        <div><strong>${fmtNumber(sale.quantity)} sold for ${fmtMoney(sale.price_each)} each</strong><span>${fmtMoney(sale.total_price)} total · ${timeAgo(sale.sold_at_ms)}</span></div>
      </div>
    </div>
  `).join("") : `<div class="empty-note">No recent sales captured.</div>`;

  $("current-listings").innerHTML = (item.current_listings || []).length ? item.current_listings.map((listing) => `
    <div class="compact-row">
      <div class="item-cell">
        ${itemIcon(item, "tiny")}
        <div><strong>${fmtMoney(listing.price_each)} each × ${fmtNumber(listing.quantity)}</strong><span>${fmtMoney(listing.total_price)} total · ${fmtDurationMs(listing.time_left)} · last seen ${timeAgo(Date.parse(listing.snapshot_at))}</span></div>
      </div>
    </div>
  `).join("") : `<div class="empty-note">No listings seen${item.listing_observed_at ? ` in latest scan` : ""}.</div>`;
}

function recipeDetail(recipe) {
  const canPriceRecipe = recipe.profit !== null && recipe.profit !== undefined;
  const recipeStats = [
    recipe.result_value !== null && recipe.result_value !== undefined ? ["Sell For", fmtMoney(recipe.result_value)] : null,
    recipe.ingredient_cost !== null && recipe.ingredient_cost !== undefined ? ["Cost to Make", fmtMoney(recipe.ingredient_cost)] : null,
    recipe.result.sales_count_24h !== null && recipe.result.sales_count_24h !== undefined ? ["Sold Today", fmtNumber(recipe.result.sales_count_24h)] : null,
    recipe.result.volume_24h !== null && recipe.result.volume_24h !== undefined ? ["Money Traded Today", fmtMoney(recipe.result.volume_24h)] : null,
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
          <span>${canPriceRecipe && recipe.profit_pct !== null && recipe.profit_pct !== undefined ? `${fmtPct(recipe.profit_pct)} could earn` : "Not enough sales to estimate"}</span>
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
          <span>${recipe.profit === null || recipe.profit === undefined ? "Price unknown" : `Could earn ${fmtMoney(recipe.profit)}`}</span>
          <span>${fmtNumber(recipe.result.sales_count_24h)} sold · ${fmtMoney(recipe.result.volume_24h)} traded</span>
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
  $("chart-meta").textContent = `${fmtMoney(item.sold_median_24h || item.market_value)} · ${fmtPct(item.change_pct)} 24h vs 7d · ${fmtNumber(item.sales_count_24h)} sold · ${fmtMoney(item.volume_24h)} traded`;
  $("item-badges").innerHTML = [
    `<span>${item.lowest_listing ? `Ask ${fmtMoney(item.lowest_listing)}` : "No active asks"}</span>`,
    item.variant_note ? `<span>${item.variant_note}</span>` : "",
  ].join("");
  renderItemDetails(item);
  drawChart(item.candles || []);
}

function navigateToItem(itemKey) {
  selectItem(itemKey, { updateUrl: true, scroll: true });
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
setInterval(refresh, 30000);
setInterval(refreshSecondary, 60000);
