"use strict";

// ───────── 小工具 ─────────
const $ = (s, r = document) => r.querySelector(s);
function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  kids.flat().forEach(c => n.append(c));
  return n;
}
const fmtMoney = x => x == null ? "—" : x >= 1e12 ? (x / 1e12).toFixed(2) + " 兆" : (x / 1e8).toFixed(1) + " 億";
const fmtPct = x => x == null ? "—" : (x > 0 ? "+" : "") + x.toFixed(2) + "%";
const cls = x => x > 0 ? "up" : x < 0 ? "down" : "";
const num = (x, d = 2) => x == null ? "—" : Number(x).toFixed(d);
const EXCH = { XNAS: "NASDAQ", XNYS: "NYSE", ARCX: "AMEX", BATS: "CBOE", XASE: "AMEX" };

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-cache" });
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}

// ───────── 分頁 ─────────
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  ["rank", "report", "screen"].forEach(t => { $("#tab-" + t).hidden = t !== b.dataset.tab; });
}));

// ───────── 排行榜 ─────────
const COLS = [
  { key: "rank", label: "#", cls: "" },
  { key: "ticker", label: "代碼", cls: "l" },
  { key: "close", label: "價格" },
  { key: "change_pct", label: "漲跌幅" },
  { key: "streak_top50", label: "在榜天數", title: "連續在前50名的交易日數" },
  { key: "dollar_volume", label: "成交金額▼" },
  { key: "market_cap", label: "市值" },
  { key: "theme", label: "題材/族群", cls: "l" },
];
let rows = [], sortKey = "dollar_volume", sortDir = -1, newTop20 = [];

function renderHead() {
  const tr = el("tr");
  COLS.forEach(c => {
    const th = el("th", { class: c.cls || "", scope: "col", tabindex: "0", title: c.title || "", text: c.label.replace("▼", "") });
    if (c.key === sortKey) { th.setAttribute("aria-sort", sortDir < 0 ? "descending" : "ascending"); th.append(sortDir < 0 ? " ▼" : " ▲"); }
    const go = () => { sortDir = sortKey === c.key ? -sortDir : (c.key === "rank" || c.key === "ticker" ? 1 : -1); sortKey = c.key; render(); };
    th.addEventListener("click", go);
    th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    tr.append(th);
  });
  const head = $("#rank-table thead"); head.replaceChildren(tr);
}

function render() {
  renderHead();
  const sorted = [...rows].sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (x == null) return 1; if (y == null) return -1;
    return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
  });
  const maxDv = Math.max(...rows.map(r => r.dollar_volume));
  $("#rank-table tbody").replaceChildren(...sorted.map(r => {
    const name = el("td", { class: "l sym" }, r.ticker);
    if (newTop20.includes(r.ticker)) name.append(el("span", { class: "badge top20", text: "新進前20" }));
    else if (r.is_new) name.append(el("span", { class: "badge", text: "新進榜" }));
    name.append(el("small", { text: r.name }));
    const tr = el("tr", { tabindex: "0" },
      el("td", { text: r.rank }), name,
      el("td", { text: num(r.close) }),
      el("td", { class: cls(r.change_pct), text: fmtPct(r.change_pct) }),
      el("td", { text: r.streak_top50 + " 天" }),
      el("td", { class: "dv" }, el("i", { style: `width:${(r.dollar_volume / maxDv * 100).toFixed(1)}%` }), el("span", { text: fmtMoney(r.dollar_volume) })),
      el("td", { text: fmtMoney(r.market_cap) }),
      el("td", { class: "theme", title: r.theme || "", text: r.theme || "—" }));
    const open = () => openChart(r);
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", e => { if (e.key === "Enter") open(); });
    return tr;
  }));
}

// ───────── 走勢圖 ─────────
const dlg = $("#chart-dlg");
let tvLoaded = null;
function loadTV() {
  tvLoaded = tvLoaded || new Promise((ok, no) => {
    const s = el("script", { src: "https://s3.tradingview.com/tv.js" });
    s.onload = ok; s.onerror = no; document.head.append(s);
  });
  return tvLoaded;
}
async function openChart(r) {
  const sym = (EXCH[r.exchange] ? EXCH[r.exchange] + ":" : "") + r.ticker;
  $("#chart-title").textContent = `${r.ticker} ${r.name}`;
  $("#chart-link").href = "https://www.tradingview.com/chart/?symbol=" + encodeURIComponent(sym);
  $("#tvbox").replaceChildren(el("div", { id: "tv", style: "height:100%" }));
  dlg.showModal();
  try {
    await loadTV();
    new TradingView.widget({ autosize: true, symbol: sym, interval: "D", timezone: "America/New_York",
      theme: "light", style: "1", locale: "zh_TW", container_id: "tv", allow_symbol_change: false });
  } catch { $("#tvbox").textContent = "走勢圖載入失敗,請改用右上角連結開啟。"; }
}
$("#chart-close").addEventListener("click", () => dlg.close());
dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });

// ───────── 報告 ─────────
async function loadReport(file) {
  const box = $("#report");
  try {
    const md = await (await fetch(file, { cache: "no-cache" })).text();
    box.innerHTML = DOMPurify.sanitize(marked.parse(md));
  } catch { box.textContent = "報告載入失敗。"; }
}
async function initReports() {
  let dates = [];
  try { dates = await getJSON("reports/index.json"); } catch {}
  const sel = $("#report-date");
  dates.forEach((d, i) => sel.append(el("option", { value: d, text: d + (i === 0 ? "(最新)" : "") })));
  sel.addEventListener("change", () => loadReport(`reports/${sel.value}.md`));
  loadReport(dates.length ? `reports/${dates[0]}.md` : "reports/latest.md");
}

// ───────── 技術篩選 ─────────
function screenTable(items, extra) {
  const head = ["代碼", "收盤", "區間(ATR倍數)", "距上緣/下緣(ATR)", "量比5/20", "週柱狀體", "日柱狀體", ...(extra ? [extra.label] : [])];
  const t = el("table", {}, el("thead", {}, el("tr", {}, head.map((h, i) => el("th", { class: i ? "" : "l", text: h })))));
  const body = el("tbody");
  items.forEach(x => body.append(el("tr", {},
    el("td", { class: "l sym", text: x.ticker }), el("td", { text: num(x.close) }),
    el("td", { text: num(x.range_atr, 1) }),
    el("td", { text: x.edge_high_atr == null ? "—" : `${num(x.edge_high_atr, 1)} / ${num(x.edge_low_atr, 1)}` }),
    el("td", { text: num(x.vol_ratio) }),
    el("td", { class: cls(x.w_hist), text: num(x.w_hist, 3) }),
    el("td", { class: cls(x.d_hist), text: num(x.d_hist, 3) }),
    ...(extra ? [el("td", { class: "l", text: extra.fn(x) })] : []))));
  t.append(body);
  return el("div", { class: "scroll" }, t);
}
function renderScreen(s) {
  const box = $("#screen"); box.replaceChildren();
  $("#screen-hint").textContent = `範圍:成交值前 ${s.universe} 名。型態A=區間整理且量縮(ATR 標準);型態B=週MACD多方、日MACD回檔。僅為技術條件篩選,非買賣建議。`;
  const section = (title, items, extra) => box.append(el("h2", { text: `${title}(${items.length})` }),
    items.length ? screenTable(items, extra) : el("p", { class: "empty", text: "今日無符合標的" }));
  section("型態A:區間整理且量縮", s.pattern_a);
  section("型態B:週線多方、日線回檔", s.pattern_b);
  box.append(el("h2", { text: `同時符合 A 與 B(${s.both.length})` }), el("p", { class: s.both.length ? "" : "empty", text: s.both.join("、") || "今日無符合標的" }));
  box.append(el("h2", { text: `接近名單・僅差一項(${s.near.length})` }));
  if (s.near.length) {
    const t = el("table", {}, el("thead", {}, el("tr", {}, ["代碼", "型態", "未通過條件"].map((h, i) => el("th", { class: "l", text: h })))));
    t.append(el("tbody", {}, s.near.map(n => el("tr", {}, el("td", { class: "l sym", text: n.ticker }), el("td", { class: "l", text: n.pattern }), el("td", { class: "l", text: `${n.failed}:${n.reason}` })))));
    box.append(el("div", { class: "scroll" }, t));
  } else box.append(el("p", { class: "empty", text: "無" }));
  if (s.insufficient.length) box.append(el("p", { class: "hint", text: "資料不足、無法驗證:" + s.insufficient.join("、") }));
}

// ───────── 啟動 ─────────
(async function init() {
  initReports();
  try {
    const d = await getJSON("data/latest.json");
    rows = d.rows; newTop20 = d.new_top20 || [];
    $("#meta").textContent = `資料日期:${d.date}(美股收盤)・全市場成交金額約 ${fmtMoney(d.total_dollar_volume)} 美元・AI ${d.ai_enabled ? "已啟用" : "未啟用"}`;
    if (d.headline?.length) { const h = $("#headline"); h.hidden = false; h.textContent = d.headline[0]; }
    const proxies = Object.entries(d.market_proxies || {}).map(([t, v]) =>
      el("span", {}, t + " ", el("b", { class: cls(v.change_pct), text: fmtPct(v.change_pct) })));
    const br = d.breadth; if (br) proxies.push(el("span", {}, "上漲/下跌家數 ", el("b", { text: `${br.advancers} / ${br.decliners}` })));
    $("#market").replaceChildren(...proxies);
    render(); renderScreen(d.screen);
  } catch (e) {
    $("#meta").textContent = "尚無資料:請先在 GitHub Actions 手動執行 backfill 與 daily。";
    $("#rank-table tbody").replaceChildren();
  }
})();
