"""步驟4:技術線型篩選(ATR 區間整理量縮 / 週MACD多方+日MACD回檔)。"""
import argparse

import pandas as pd

from common import DATA, latest_ranking, load_config, load_prices, read_json, write_json


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def macd(close, fast, slow, sig):
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, sig)
    return dif, dea, dif - dea


def atr(df, n):
    """Wilder 平滑 ATR。"""
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def evaluate(df, cfg):
    """回傳指標與各條件是否成立;資料不足回傳 None。"""
    pa, pb = cfg["pattern_a"], cfg["pattern_b"]
    if df is None or len(df) < 120:
        return None
    df = df.reset_index(drop=True)
    c = df["close"]
    close = float(c.iloc[-1])
    a = float(atr(df, pa["atr_period"]).iloc[-1])
    w = df.tail(pa["range_days"])
    hi, lo = float(w["high"].max()), float(w["low"].min())
    ma60 = c.rolling(60).mean()
    ma60_now, ma60_slope = float(ma60.iloc[-1]), float(ma60.iloc[-1] - ma60.iloc[-6])
    vr = float(df["volume"].tail(5).mean() / df["volume"].tail(20).mean())
    buf = pa["edge_buffer_atr"] * a

    A = {
        "A1": (hi - lo) / a <= pa["max_range_atr_multiple"],
        "A2": lo <= close <= hi and (hi - close) >= buf and (close - lo) >= buf,
        "A3": vr <= pa["max_volume_ratio"],
        "A4": close >= ma60_now or ma60_slope >= 0,
    }

    f, s, g = pb["macd"]
    dif, dea, hist = macd(c, f, s, g)
    wk = c.set_axis(pd.to_datetime(df["date"])).resample("W-FRI").last().dropna()
    B, wm = None, {}
    if len(wk) >= pb["min_weekly_bars"]:
        wdif, wdea, whist = macd(wk, f, s, g)
        d = pb["daily_hist_decline_days"]
        declining = bool((hist.diff().iloc[-d:] < 0).all())
        B = {
            "B1": bool(wdif.iloc[-1] > wdea.iloc[-1] and whist.iloc[-1] >= whist.iloc[-2]),
            "B2": bool((declining or hist.iloc[-1] < 0) and dif.iloc[-1] < dif.tail(10).max()),
            "B3": bool(close >= ma60_now and dif.iloc[-1] >= -pb["dif_floor_pct"] / 100 * close),
        }
        wm = {"w_dif": wdif.iloc[-1], "w_dea": wdea.iloc[-1], "w_hist": whist.iloc[-1], "w_hist_prev": whist.iloc[-2]}

    m = {
        "close": close, "atr": a, "range_pct": (hi - lo) / lo * 100, "range_atr": (hi - lo) / a,
        "edge_low_atr": (close - lo) / a, "edge_high_atr": (hi - close) / a, "vol_ratio": vr,
        "ma60": ma60_now, "d_dif": dif.iloc[-1], "d_dea": dea.iloc[-1], "d_hist": hist.iloc[-1], **wm,
    }
    return {"metrics": {k: round(float(v), 3) for k, v in m.items()},
            "A": {k: bool(v) for k, v in A.items()}, "B": B}


REASON = {
    "A1": "區間過寬", "A2": "貼近區間邊緣或已突破/跌破", "A3": "量未縮",
    "A4": "跌破60MA且均線下彎", "B1": "週MACD未維持多方", "B2": "日MACD未呈回檔修正",
    "B3": "日線結構轉弱(破60MA或DIF過低)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)   # 保留參數,實際讀取 repo 根目錄 config.yml
    ap.parse_args()
    cfg = load_config()
    date, path = latest_ranking()
    rows = read_json(path)["rows"][: cfg["screen_top_n"]]

    out = {"date": date, "universe": len(rows), "pattern_a": [], "pattern_b": [], "both": [],
           "near": [], "insufficient": []}
    for r in rows:
        t = r["ticker"]
        res = evaluate(load_prices(t), cfg)
        if res is None:
            out["insufficient"].append(t)
            continue
        item = {"ticker": t, "name": r["name"], **res["metrics"], "conds": {**res["A"], **(res["B"] or {})}}
        a_ok = all(res["A"].values())
        b_ok = bool(res["B"]) and all(res["B"].values())
        if res["B"] is None:
            out["insufficient"].append(t + "(週線資料不足)")
        if a_ok:
            out["pattern_a"].append(item)
        if b_ok:
            out["pattern_b"].append(item)
        if a_ok and b_ok:
            out["both"].append(t)
        for name, conds in (("A", res["A"]), ("B", res["B"])):
            if conds and not all(conds.values()):
                failed = [k for k, v in conds.items() if not v]
                if len(failed) == 1:
                    out["near"].append({"ticker": t, "pattern": name, "failed": failed[0],
                                        "reason": REASON[failed[0]], **{k: item[k] for k in ("range_atr", "vol_ratio", "d_hist")}})
    write_json(DATA / "screen" / f"{date}.json", out)
    print(f"A:{[x['ticker'] for x in out['pattern_a']]} B:{[x['ticker'] for x in out['pattern_b']]} 同時:{out['both']}")


if __name__ == "__main__":
    main()
