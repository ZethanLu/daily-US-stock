# 美股成交值排行 Top 50

每日自動抓取前一美股交易日全市場資料 → 成交金額前 50 名 → 新進榜/在榜天數/±3% 波動 → ATR+MACD 技術篩選 → Gemini 盤後報告 → GitHub Pages 網站。

## 設定步驟
1. 建立 GitHub repo,把本資料夾全部內容推上去(含隱藏資料夾 `.github`)。
2. Settings → Secrets and variables → Actions,新增 `POLYGON_API_KEY`、`GEMINI_API_KEY`(沒有 Gemini 金鑰也能跑,只是報告為純數據)。
3. Settings → Pages → Source 選 `Deploy from a branch`,分支 `main`、資料夾 `/ (root)`。
4. Actions → `US Stock Daily Pipeline` → Run workflow → mode 選 `backfill`(免費方案約 40~60 分鐘,只需一次)。
5. 再手動執行一次 `daily`,確認 `data/latest.json` 與 `reports/latest.md` 產生,網站即可開啟。
6. 之後週二~週六台北 13:00 自動執行;週日自動重整歷史價格。

## 調整
所有門檻都在 `config.yml`(是否排除 ETF、±% 門檻、ATR 倍數、量縮比、MACD 參數)。
免費方案請保留 `polygon_min_interval_sec: 12.5`;付費方案可改 0 並把 cron 提前。

## 目錄
- `scripts/`:fetch_rankings、backfill_prices、update_prices、refresh_prices、analyze、screen、ai_report(+ common.py 共用工具)
- `data/`:rankings(每日前50)、prices(日K)、analysis、screen、meta.json、themes.json、latest.json
- `reports/`:每日報告 Markdown 與 index.json
- `index.html / app.js / style.css`:網站前端
