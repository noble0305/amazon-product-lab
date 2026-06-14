const state = {
  analysis: null,
  enrichmentCsv: "",
  datasetType: "market",
  downloadName: "candidate_enrichment.csv",
  filtered: [],
  sort: { key: "rank", direction: "ascending" },
  selectedAsins: new Set(),
  concepts: [],
  currentConcept: null,
};
const $ = (id) => document.getElementById(id);

const fileInput = $("file-input");
const dropZone = $("drop-zone");
const statusBox = $("status");
const workspace = $("workspace");

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => switchView(button.dataset.view));
});

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
$("results-body").addEventListener("change", (event) => {
  if (!event.target.matches(".row-select")) return;
  if (event.target.checked) state.selectedAsins.add(event.target.value);
  else state.selectedAsins.delete(event.target.value);
  updateConceptSelection();
});

$("download-button").addEventListener("click", () => {
  const blob = new Blob(["\ufeff" + state.enrichmentCsv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = state.downloadName;
  link.click();
  URL.revokeObjectURL(link.href);
});
$("create-concept-button").addEventListener("click", openConceptDialog);
$("new-concept-button").addEventListener("click", () => {
  state.selectedAsins.clear();
  openConceptDialog();
});
$("close-concept-dialog").addEventListener("click", () => $("concept-dialog").close());
$("create-concept-form").addEventListener("submit", createConcept);
$("concept-form").addEventListener("submit", saveConceptDefinition);
$("quote-form").addEventListener("submit", saveQuote);
$("profit-form").addEventListener("submit", saveProfitSnapshot);
$("approve-concept-button").addEventListener("click", approveConcept);
$("listing-form").addEventListener("submit", saveListing);
$("launch-form").addEventListener("submit", createLaunchPackage);
$("mark-launched-button").addEventListener("click", () => conceptAction("status", { status: "launched" }));
$("result-form").addEventListener("submit", saveExperimentResult);
$("refresh-concept-button").addEventListener("click", () => loadConcept(state.currentConcept.id));

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
    applyAnalysisPayload(payload);
    const unit = state.datasetType === "asin" ? "个 ASIN" : "个市场";
    showStatus(`分析完成：已读取 ${payload.analysis.source.data_rows} ${unit}。`);
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showStatus(error.message, true);
  }
}

function applyAnalysisPayload(payload) {
  state.analysis = payload.analysis;
  state.enrichmentCsv = payload.enrichment_csv;
  state.datasetType = payload.dataset_type;
  state.downloadName = payload.download_name;
  state.sort = { key: "rank", direction: "ascending" };
  state.selectedAsins.clear();
  renderHeaders();
  renderSummary();
  applyFilters();
  workspace.hidden = false;
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
      <td><input class="row-select" type="checkbox" value="${escapeHtml(product.asin)}" aria-label="选择 ${escapeHtml(product.asin)}" ${state.selectedAsins.has(product.asin) ? "checked" : ""}></td>
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
  updateConceptSelection();
}

function renderHeaders() {
  if (state.datasetType === "asin") {
    $("results-head").innerHTML = `<tr>
      <th>选择</th>${sortHeader("rank", "排名")}${sortHeader("title", "商品")}${sortHeader("opportunity_score", "机会分")}
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

function updateConceptSelection() {
  const button = $("create-concept-button");
  button.hidden = state.datasetType !== "asin";
  button.textContent = state.selectedAsins.size
    ? `从已选 ${state.selectedAsins.size} 个 ASIN 创建方案`
    : "选择 ASIN 后创建方案";
  button.disabled = state.selectedAsins.size === 0;
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

function switchView(view) {
  $("analysis-view").hidden = view !== "analysis";
  $("concepts-view").hidden = view !== "concepts";
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (view === "concepts") loadConcepts();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

async function initialize() {
  try {
    const latest = await api("/api/analysis/latest");
    if (latest) {
      applyAnalysisPayload(latest);
      showStatus(`已恢复上次分析：${latest.analysis.source.file}`);
    }
    await loadConcepts();
  } catch (error) {
    showStatus(error.message, true);
  }
}

function openConceptDialog() {
  const count = state.selectedAsins.size;
  $("selected-benchmark-count").textContent = count
    ? `将保存 ${count} 个对标 ASIN 的当前数据快照。`
    : "当前为空白方案，稍后可补充对标信息。";
  $("concept-dialog").showModal();
}

async function createConcept(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formDataObject(form, ["target_price"]);
  data.benchmarks = state.datasetType === "asin" && state.analysis
    ? state.analysis.products.filter((item) => state.selectedAsins.has(item.asin))
    : [];
  try {
    const concept = await api("/api/concepts", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    $("concept-dialog").close();
    state.selectedAsins.clear();
    await loadConcepts();
    switchView("concepts");
    await loadConcept(concept.id);
  } catch (error) {
    alert(error.message);
  }
}

async function loadConcepts() {
  const payload = await api("/api/concepts");
  state.concepts = payload.concepts;
  $("concept-count").textContent = state.concepts.length;
  const list = $("concept-list");
  list.replaceChildren();
  state.concepts.forEach((concept) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `concept-list-button ${state.currentConcept?.id === concept.id ? "active" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(concept.name)}</strong><small>${escapeHtml(concept.status)} · $${Number(concept.target_price).toFixed(2)}</small>`;
    button.addEventListener("click", () => loadConcept(concept.id));
    list.appendChild(button);
  });
}

async function loadConcept(id) {
  try {
    state.currentConcept = await api(`/api/concepts/${id}`);
    renderConcept();
    await loadConcepts();
  } catch (error) {
    alert(error.message);
  }
}

function renderConcept() {
  const concept = state.currentConcept;
  $("concept-empty").hidden = true;
  $("concept-detail").hidden = false;
  $("concept-name").textContent = concept.name;
  $("concept-status").textContent = concept.status;
  renderWorkflow(concept.status);
  setFormValues($("concept-form"), concept);
  renderBenchmarks(concept.benchmarks);
  renderQuotes(concept.supplier_quotes);
  renderProfit(concept.profit_snapshots[0]);
  renderActualResult(concept.experiment_results[0]);
  const latestListing = concept.listing_versions[0];
  if (latestListing) setFormValues($("listing-form"), latestListing);
  const profitForm = $("profit-form");
  if (!profitForm.elements.sale_price.value) profitForm.elements.sale_price.value = concept.target_price;
  if (concept.supplier_quotes.length) {
    const quote = concept.supplier_quotes[0];
    const landed = quote.unit_cost + quote.domestic_shipping + quote.international_shipping + quote.tariff + quote.packaging;
    profitForm.elements.landed_cost.value = landed.toFixed(2);
  }
}

function renderWorkflow(status) {
  const steps = ["idea", "sourcing", "quoted", "approved", "listing_ready", "launch_ready", "launched", "reviewing", "scale", "stop"];
  $("workflow-progress").innerHTML = steps.map((step) => `<span class="workflow-step ${step === status ? "current" : ""}">${step}</span>`).join("");
}

function renderBenchmarks(benchmarks) {
  $("benchmark-list").innerHTML = benchmarks.length
    ? benchmarks.map((item) => `<div class="record-card"><strong>${escapeHtml(item.asin)} · ${escapeHtml(item.title || "")}</strong><p>机会分 ${Number(item.opportunity_score || 0).toFixed(2)} · 点击 ${formatOptional(item.search_clicks_360d)} · 评价 ${formatOptional(item.review_count)}</p></div>`).join("")
    : '<div class="record-card"><p>尚未绑定对标 ASIN。</p></div>';
}

function renderQuotes(quotes) {
  $("quote-list").innerHTML = quotes.length
    ? quotes.map((quote) => {
      const landed = quote.unit_cost + quote.domestic_shipping + quote.international_shipping + quote.tariff + quote.packaging;
      const link = quote.product_url ? `<a href="${escapeHtml(quote.product_url)}" target="_blank" rel="noopener noreferrer">查看 1688</a>` : "";
      return `<div class="record-card"><strong>${escapeHtml(quote.supplier_name)} · 到岸成本 $${landed.toFixed(2)}</strong><p>单价 $${quote.unit_cost.toFixed(2)} · MOQ ${quote.moq} · 交期 ${quote.lead_time_days} 天 ${link}</p></div>`;
    }).join("")
    : '<div class="record-card"><p>尚未保存供应商报价。</p></div>';
}

function renderProfit(snapshot) {
  if (!snapshot) {
    $("profit-result").innerHTML = '<p class="helper">录入成本后生成三情景利润快照。</p>';
    return;
  }
  $("profit-result").innerHTML = `<div class="profit-cards">${["optimistic", "base", "pessimistic"].map((mode) => {
    const item = snapshot.scenarios[mode];
    return `<div class="profit-card"><span>${mode}</span><strong>$${item.profit.toFixed(2)}</strong><small>利润率 ${(item.margin * 100).toFixed(1)}%</small></div>`;
  }).join("")}</div>${snapshot.red_flags.length ? `<div class="profit-warning">红线：${snapshot.red_flags.join(", ")}</div>` : `<p class="helper">最大可接受到岸成本：$${snapshot.max_landed_cost_at_15_percent_margin.toFixed(2)}</p>`}`;
}

function renderActualResult(result) {
  $("actual-result").innerHTML = result
    ? `<div class="profit-cards"><div class="profit-card"><span>实际贡献利润</span><strong>$${result.contribution_profit.toFixed(2)}</strong><small>利润率 ${(result.contribution_margin * 100).toFixed(1)}%</small></div><div class="profit-card"><span>每件利润</span><strong>$${result.profit_per_unit.toFixed(2)}</strong></div><div class="profit-card"><span>预测偏差</span><strong>${result.profit_variance === undefined ? "—" : `$${result.profit_variance.toFixed(2)}`}</strong><small>实际减预测</small></div></div>`
    : '<p class="helper">上架后录入真实结果，用于验证预测可靠性。</p>';
}

async function saveConceptDefinition(event) {
  event.preventDefault();
  const data = formDataObject(event.currentTarget, ["target_price"], ["hazmat"]);
  await conceptAction("update", data);
}

async function saveQuote(event) {
  event.preventDefault();
  const numeric = ["unit_cost", "domestic_shipping", "international_shipping", "tariff", "packaging", "moq", "lead_time_days"];
  await conceptAction("quotes", formDataObject(event.currentTarget, numeric));
  event.currentTarget.reset();
}

async function saveProfitSnapshot(event) {
  event.preventDefault();
  const numeric = ["sale_price", "landed_cost", "fba_fee", "referral_fee_rate", "storage_cost", "return_rate", "return_loss_rate", "conversion_rate", "cpc"];
  const data = formDataObject(event.currentTarget, numeric);
  data.compliance_risk = state.currentConcept.compliance_risk;
  data.ip_risk = state.currentConcept.ip_risk;
  data.hazmat = state.currentConcept.hazmat;
  await conceptAction("profit", data);
}

async function approveConcept() {
  await conceptAction("status", { status: "approved" });
}

async function saveListing(event) {
  event.preventDefault();
  const data = formDataObject(event.currentTarget, [], ["approved"]);
  data.bullet_points = data.bullet_points.split("\n").map((item) => item.trim()).filter(Boolean);
  data.image_paths = data.image_paths.split("\n").map((item) => item.trim()).filter(Boolean);
  data.image_rights_confirmed = event.currentTarget.elements.image_rights_confirmed.checked;
  await conceptAction("listing", data);
  if (data.approved && state.currentConcept.status === "approved") {
    await conceptAction("status", { status: "listing_ready" });
  }
}

async function createLaunchPackage(event) {
  event.preventDefault();
  try {
    const data = formDataObject(event.currentTarget, ["inventory_quantity"]);
    const packageData = await api(`/api/concepts/${state.currentConcept.id}/launch-package`, { method: "POST", body: JSON.stringify(data) });
    downloadJson(`launch-package-${state.currentConcept.sku || state.currentConcept.id}.json`, packageData);
    await loadConcept(state.currentConcept.id);
  } catch (error) {
    alert(error.message);
  }
}

async function saveExperimentResult(event) {
  event.preventDefault();
  const numeric = ["units_sold", "revenue", "product_cost", "fba_fees", "referral_fees", "storage_cost", "ad_spend", "return_loss", "other_cost"];
  await conceptAction("results", formDataObject(event.currentTarget, numeric));
}

async function conceptAction(action, data) {
  if (!state.currentConcept) return;
  try {
    await api(`/api/concepts/${state.currentConcept.id}/${action}`, { method: "POST", body: JSON.stringify(data) });
    await loadConcept(state.currentConcept.id);
  } catch (error) {
    alert(error.message);
  }
}

function formDataObject(form, numericFields = [], checkboxFields = []) {
  const data = Object.fromEntries(new FormData(form).entries());
  numericFields.forEach((field) => { data[field] = Number(data[field] || 0); });
  checkboxFields.forEach((field) => { data[field] = form.elements[field].checked; });
  return data;
}

function setFormValues(form, data) {
  Array.from(form.elements).forEach((element) => {
    if (!element.name || data[element.name] === undefined || data[element.name] === null) return;
    if (element.type === "checkbox") element.checked = Boolean(data[element.name]);
    else if (Array.isArray(data[element.name])) element.value = data[element.name].join("\n");
    else element.value = data[element.name];
  });
}

function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

initialize();
