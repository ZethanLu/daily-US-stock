"""共用工具:設定、Polygon 客戶端(含限速與重試)、日期、價格檔讀寫。"""
import datetime as dt
import json
import os
import re
import sys
import time
import zoneinfo
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
ET = zoneinfo.ZoneInfo("America/New_York")
COLS = ["date", "open", "high", "low", "close", "volume"]


# ───────── 基本 I/O ─────────
def load_config():
    return yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))


def read_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def set_output(key, value):
    """寫入 GitHub Actions step output,供後續步驟判斷是否略過。"""
    print(f"[output] {key}={value}")
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


# ───────── Polygon ─────────
class Polygon:
    BASE = "https://api.polygon.io"

    def __init__(self, min_interval=12.5):
        key = os.environ.get("POLYGON_API_KEY")
        if not key:
            sys.exit("缺少環境變數 POLYGON_API_KEY")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {key}"
        self.interval = float(min_interval)
        self._last = 0.0

    def get(self, path, params=None, retries=5):
        for i in range(retries):
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.s.get(self.BASE + path, params=params, timeout=60)
            except requests.RequestException as e:
                print(f"  網路錯誤:{e};重試 {i + 1}/{retries}")
                time.sleep(5 * (i + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(15 * (i + 1))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Polygon 請求失敗:{path}")


# ───────── 日期 ─────────
def last_session_candidate():
    """回傳『最近一個已結束的美股平日』(可由環境變數 TARGET_DATE 指定)。"""
    forced = (os.environ.get("TARGET_DATE") or "").strip()
    if forced:
        return dt.date.fromisoformat(forced)
    d = dt.datetime.now(ET).date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def grouped(client, d):
    """某日全美股 OHLCV;休市或尚未提供時回傳 {}。"""
    j = client.get(f"/v2/aggs/grouped/locale/us/market/stocks/{d}", {"adjusted": "true"})
    return {r["T"]: r for r in (j or {}).get("results") or [] if r.get("v") and r.get("c")}


def previous_grouped(client, d, max_back=6):
    x = d
    for _ in range(max_back):
        x -= dt.timedelta(days=1)
        if x.weekday() >= 5:
            continue
        g = grouped(client, x)
        if g:
            return x.isoformat(), g
    return None, {}


def dollar_volume(bar):
    return float(bar.get("vw") or bar["c"]) * float(bar["v"])


# ───────── 證券資料(快取) ─────────
def get_meta(client, ticker, meta, max_age_days=30):
    m = meta.get(ticker)
    today = dt.date.today()
    if m and (today - dt.date.fromisoformat(m["fetched"])).days <= max_age_days:
        return m
    j = client.get(f"/v3/reference/tickers/{ticker}")
    r = (j or {}).get("results") or {}
    m = {
        "name": r.get("name", ticker),
        "type": r.get("type", "UNKNOWN"),
        "exchange": r.get("primary_exchange"),
        "shares": r.get("weighted_shares_outstanding") or r.get("share_class_shares_outstanding"),
        "market_cap": r.get("market_cap"),
        "fetched": today.isoformat(),
    }
    meta[ticker] = m
    return m


def select_top(client, g, n, cfg, meta):
    """依成交金額排序,逐檔確認證券類型後取前 n 名。"""
    allowed = set(cfg["include_types"]) | (set() if cfg["exclude_etf"] else {"ETF", "ETN", "ETV"})
    cands = sorted(
        (t for t in g if re.fullmatch(r"[A-Z]{1,5}", t) and g[t]["c"] >= cfg["min_price"]),
        key=lambda t: -dollar_volume(g[t]),
    )
    out = []
    for t in cands:
        m = get_meta(client, t, meta)
        if m.get("type") in allowed:
            out.append(t)
            if len(out) >= n:
                break
    write_json(DATA / "meta.json", meta)
    return out


# ───────── 歷史價格 ─────────
def fetch_history(client, ticker, days):
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    j = client.get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    rows = [
        {
            "date": dt.datetime.fromtimestamp(r["t"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"], "volume": r["v"],
        }
        for r in (j or {}).get("results") or []
    ]
    return pd.DataFrame(rows, columns=COLS)


def prices_path(ticker):
    return DATA / "prices" / f"{ticker}.csv"


def load_prices(ticker):
    p = prices_path(ticker)
    return pd.read_csv(p) if p.exists() else None


def save_prices(ticker, df):
    p = prices_path(ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = df[COLS].drop_duplicates("date", keep="last").sort_values("date")
    df.to_csv(p, index=False)


# ───────── 排行檔 ─────────
def ranking_files():
    return sorted((DATA / "rankings").glob("*.json"))


def latest_ranking():
    files = ranking_files()
    if not files:
        sys.exit("找不到任何排行檔,請先執行 fetch_rankings.py")
    return files[-1].stem, files[-1]
