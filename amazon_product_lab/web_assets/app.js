const state = {
  analysis: null,
  enrichmentCsv: "",
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

["search-input", "price-filter", "risk-filter", "score-filter"].forEach((id) => {
  $(id).addEventListener("input", applyFilters);
});
document.querySelectorAll(".sort-button").forEach((button) => {
  button.addEventListener("click", () => sortFilter(button.dataset.sort));
});

$("download-button").addEventListener("click", () => {
  const blob = new Blob(["\ufeff" + state.enrichmentCsv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "candidate_enrichment.csv";
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
    renderSummary();
    applyFilters();
    workspace.hidden = false;
    showStatus(`分析完成：已读取 ${payload.analysis.source.data_rows} 个市场。`);
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
  const markets = state.analysis.markets;
  $("metric-total").textContent = markets.length;
  $("metric-price").textContent = markets.filter((m) => m.average_price >= 20 && m.average_price <= 50).length;
  $("metric-growth").textContent = markets.filter((m) => m.search_growth_90d > 0).length;
  $("metric-risk").textContent = markets.filter((m) => m.manual_review_flags.length > 0).length;
  const source = state.analysis.source;
  $("source-meta").textContent = `${source.file} · ${source.collection_date || "日期未知"}`;
}

function applyFilters() {
  if (!state.analysis) return;
  const query = $("search-input").value.trim().toLowerCase();
  const price = $("price-filter").value;
  const risk = $("risk-filter").value;
  const minScore = Number($("score-filter").value);
  state.filtered = state.analysis.markets.filter((market) => {
    const haystack = `${market.niche} ${market.keywords.join(" ")}`.toLowerCase();
    const priceMatch = price === "all"
      || (price === "target" && market.average_price >= 20 && market.average_price <= 50)
      || (price === "low" && market.average_price < 20)
      || (price === "high" && market.average_price > 50);
    const flagged = market.manual_review_flags.length > 0;
    const riskMatch = risk === "all" || (risk === "flagged" && flagged) || (risk === "clear" && !flagged);
    return haystack.includes(query) && priceMatch && riskMatch && market.screening_score >= minScore;
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
  return market[key];
}

function renderTable() {
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
