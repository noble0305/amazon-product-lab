const state = {
  analysis: null,
  enrichmentCsv: "",
  datasetType: "market",
  downloadName: "candidate_enrichment.csv",
  filtered: [],
  sort: { key: "rank", direction: "ascending" },
};
const $ = (id) => document.getElementById(id);

const fileInput = $("file-input");
const dropZone = $("drop-zone");
const statusBox = $("status");
const workspace = $("workspace");

$("choose-file-button").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) analyzeFile(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
});
["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
});
dropZone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) analyzeFile(file);
});

["search-input", "price-filter", "risk-filter", "score-filter", "completeness-filter"].forEach((id) => {
  $(id).addEventListener("input", applyFilters);
});
$("results-head").addEventListener("click", (event) => {
  const button = event.target.closest(".sort-button");
  if (button) sortFilter(button.dataset.sort);
});

$("download-button").addEventListener("click", () => {
  const blob = new Blob(["\ufeff" + state.enrichmentCsv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.downloadName;
  link.click();
  URL.revokeObjectURL(link.href);
});

async function analyzeFile(file) {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    showStatus("请选择 CSV 文件。", true);
    return;
  }
  showStatus(`正在分析 ${file.name}…`);
  workspace.hidden = true;
  try {
    const response = await fetch(`/api/analyze?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "text/csv" },
      body: file,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "分析失败");
    state.analysis = payload.analysis;
    state.enrichmentCsv = payload.enrichment_csv;
    state.datasetType = payload.dataset_type;
    state.downloadName = payload.download_name;
    state.sort = { key: "rank", direction: "ascending" };
    renderHeaders();
    renderSummary();
    applyFilters();
    workspace.hidden = false;
    const unit = state.datasetType === "asin" ? "个 ASIN" : "个市场";
    showStatus(`分析完成：已读取 ${payload.analysis.source.data_rows} ${unit}。`);
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showStatus(error.message, true);
  }
}

function showStatus(message, isError = false) {
  statusBox.hidden = false;
  statusBox.textContent = message;
  statusBox.classList.toggle("error", isError);
}

function renderSummary() {
  const items = state.datasetType === "asin" ? state.analysis.products : state.analysis.markets;
  const priceKey = state.datasetType === "asin" ? "average_price_90d" : "average_price";
  $("metric-total-label").textContent = state.datasetType === "asin" ? "ASIN 总数" : "市场总数";
  $("metric-total").textContent = items.length;
  $("metric-price").textContent = items.filter((item) => item[priceKey] >= 20 && item[priceKey] <= 50).length;
  if (state.datasetType === "asin") {
    $("metric-demand-label").textContent = "有需求证据";
    $("metric-demand-note").textContent = "点击或有效 BSR";
    $("metric-growth").textContent = items.filter((item) => item.demand_score !== null).length;
    $("results-title").textContent = "ASIN 产品机会";
    $("download-button").textContent = "下载 Top 30 成本补录模板";
  } else {
    $("metric-demand-label").textContent = "正向增长";
    $("metric-demand-note").textContent = "近 90 天";
    $("metric-growth").textContent = items.filter((item) => item.search_growth_90d > 0).length;
    $("results-title").textContent = "候选市场";
    $("download-button").textContent = "下载 Top 30 补录模板";
  }
  $("metric-risk").textContent = items.filter((item) => item.manual_review_flags.length > 0).length;
  const source = state.analysis.source;
  $("source-meta").textContent = `${source.file} · ${source.collection_date || "日期未知"}`;
}

function applyFilters() {
  if (!state.analysis) return;
  const query = $("search-input").value.trim().toLowerCase();
  const price = $("price-filter").value;
  const risk = $("risk-filter").value;
  const minScore = Number($("score-filter").value);
  const minCompleteness = Number($("completeness-filter").value);
  const items = state.datasetType === "asin" ? state.analysis.products : state.analysis.markets;
  state.filtered = items.filter((item) => {
    const haystack = state.datasetType === "asin"
      ? `${item.title} ${item.asin} ${item.brand} ${item.category}`.toLowerCase()
      : `${item.niche} ${item.keywords.join(" ")}`.toLowerCase();
    const itemPrice = state.datasetType === "asin" ? item.average_price_90d : item.average_price;
    const priceMatch = price === "all"
      || (price === "target" && itemPrice >= 20 && itemPrice <= 50)
      || (price === "low" && itemPrice !== null && itemPrice < 20)
      || (price === "high" && itemPrice > 50);
    const flagged = item.manual_review_flags.length > 0;
    const riskMatch = risk === "all" || (risk === "flagged" && flagged) || (risk === "clear" && !flagged);
    const itemScore = state.datasetType === "asin" ? item.opportunity_score : item.screening_score;
    const completeness = state.datasetType === "asin" ? item.data_completeness : 100;
    return haystack.includes(query) && priceMatch && riskMatch && itemScore >= minScore && completeness >= minCompleteness;
  });
  sortMarkets();
  renderTable();
}

function sortFilter(key) {
  if (state.sort.key === key) {
    state.sort.direction = state.sort.direction === "ascending" ? "descending" : "ascending";
  } else {
    state.sort.key = key;
    state.sort.direction = key === "niche" || key === "rank" ? "ascending" : "descending";
  }
  sortMarkets();
  renderTable();
}

function sortMarkets() {
  const { key, direction } = state.sort;
  const factor = direction === "ascending" ? 1 : -1;
  state.filtered.sort((left, right) => {
    const leftValue = sortableValue(left, key);
    const rightValue = sortableValue(right, key);
    if (typeof leftValue === "string") return leftValue.localeCompare(rightValue, "en") * factor;
    return (leftValue - rightValue) * factor;
  });
  document.querySelectorAll("th[aria-sort]").forEach((header) => {
    const active = header.querySelector(`[data-sort="${key}"]`);
    header.setAttribute("aria-sort", active ? direction : "none");
  });
}

function sortableValue(market, key) {
  if (key === "manual_review_flags") return market.manual_review_flags.length;
  const value = market[key];
  if (value === null || value === undefined) return state.sort.direction === "ascending" ? Infinity : -Infinity;
  return value;
}

function renderTable() {
  if (state.datasetType === "asin") {
    renderAsinTable();
    return;
  }
  const body = $("results-body");
  body.replaceChildren();
  state.filtered.slice(0, 200).forEach((market) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="rank">${market.rank}</td>
      <td class="niche-cell"><strong>${escapeHtml(market.niche)}</strong>${renderKeywordLinks(market.keywords)}</td>
      <td class="score number">${market.screening_score.toFixed(2)}</td>
      <td class="number">${market.demand_score.toFixed(2)}</td>
      <td class="number">$${market.average_price.toFixed(2)}</td>
      <td class="growth number ${market.search_growth_90d < 0 ? "negative" : ""}">${formatPercent(market.search_growth_90d)}</td>
      <td class="number">${formatPercent(market.return_rate)}</td>
      <td>${renderRisk(market.manual_review_flags)}</td>`;
    body.appendChild(row);
  });
  $("result-count").textContent = `显示 ${Math.min(state.filtered.length, 200)} / ${state.filtered.length} 个市场`;
  $("empty-state").hidden = state.filtered.length !== 0;
}

function renderAsinTable() {
  const body = $("results-body");
  body.replaceChildren();
  state.filtered.slice(0, 200).forEach((product) => {
    const row = document.createElement("tr");
    const asinUrl = `https://www.amazon.com/dp/${encodeURIComponent(product.asin)}`;
    row.innerHTML = `
      <td class="rank">${product.rank}</td>
      <td class="product-cell"><strong><a class="product-title-link" href="${asinUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(product.title)}</a></strong><div class="product-meta"><a class="asin-link" href="${asinUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(product.asin)}</a><span>${escapeHtml(product.brand || "品牌未知")}</span><span>${escapeHtml(product.category || "类目未知")}</span></div></td>
      <td class="score number">${product.opportunity_score.toFixed(2)}</td>
      <td class="number">${product.data_completeness.toFixed(0)}%</td>
      <td class="number">${formatOptional(product.search_clicks_360d)}</td>
      <td class="number">${formatOptional(product.competition_score, 2)}</td>
      <td class="number">${formatMoney(product.average_price_90d)}</td>
      <td class="number">${formatOptional(product.review_count)}</td>
      <td class="number">${formatOptional(product.rating, 2)}</td>
      <td class="number">${formatOptional(product.bsr)}</td>
      <td>${renderRisk(product.manual_review_flags)}</td>`;
    body.appendChild(row);
  });
  $("result-count").textContent = `显示 ${Math.min(state.filtered.length, 200)} / ${state.filtered.length} 个 ASIN`;
  $("empty-state").hidden = state.filtered.length !== 0;
}

function renderHeaders() {
  if (state.datasetType === "asin") {
    $("results-head").innerHTML = `<tr>
      ${sortHeader("rank", "排名")}${sortHeader("title", "商品")}${sortHeader("opportunity_score", "机会分")}
      ${sortHeader("data_completeness", "完整度")}${sortHeader("search_clicks_360d", "点击量")}
      ${sortHeader("competition_score", "竞争分")}${sortHeader("average_price_90d", "90天均价")}
      ${sortHeader("review_count", "评价数")}${sortHeader("rating", "评分")}${sortHeader("bsr", "BSR")}
      ${sortHeader("manual_review_flags", "风险复核")}</tr>`;
  } else {
    $("results-head").innerHTML = `<tr>
      ${sortHeader("rank", "排名")}${sortHeader("niche", "细分市场")}${sortHeader("screening_score", "初筛分")}
      ${sortHeader("demand_score", "需求分")}${sortHeader("average_price", "均价")}
      ${sortHeader("search_growth_90d", "90 天增长")}${sortHeader("return_rate", "退货率")}
      ${sortHeader("manual_review_flags", "风险复核")}</tr>`;
  }
}

function sortHeader(key, label) {
  return `<th aria-sort="none"><button class="sort-button" data-sort="${key}" type="button">${label}<span aria-hidden="true">↕</span></button></th>`;
}

function formatOptional(value, decimals = 0) {
  return value === null || value === undefined ? '<span class="missing">—</span>' : Number(value).toFixed(decimals);
}

function formatMoney(value) {
  return value === null || value === undefined ? '<span class="missing">—</span>' : `$${Number(value).toFixed(2)}`;
}

function renderKeywordLinks(keywords) {
  const links = keywords.filter(Boolean).map((keyword) => {
    const url = `https://www.amazon.com/s?k=${encodeURIComponent(keyword)}`;
    return `<a class="keyword-link" href="${url}" target="_blank" rel="noopener noreferrer" title="在 Amazon 搜索 ${escapeHtml(keyword)}">${escapeHtml(keyword)}</a>`;
  });
  return `<div class="keyword-links">${links.join('<span class="keyword-separator" aria-hidden="true">·</span>')}</div>`;
}

function renderRisk(flags) {
  if (!flags.length) return '<span class="tag clear">无提示</span>';
  const labels = {
    pest_control_review: "驱虫/农药",
    ingestible_review: "食品/补充剂",
    privacy_review: "隐私监控",
  };
  return flags.map((flag) => `<span class="tag">${labels[flag] || escapeHtml(flag)}</span>`).join(" ");
}

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}
