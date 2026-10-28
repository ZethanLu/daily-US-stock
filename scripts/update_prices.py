"""步驟2:把前 N 名的當日 K 線併入歷史庫;缺資料或有缺口者自動全量回補。"""
import argparse
import datetime as dt

import pandas as pd

from common import (COLS, Polygon, fetch_history, latest_ranking, load_config, load_prices,
                    read_json, save_prices)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-bars", type=int, default=300)
    ap.add_argument("--days", type=int, default=460)
    args = ap.parse_args()
    cfg = load_config()
    date, path = latest_ranking()
    rk = read_json(path)
    prev = rk.get("prev_date") or ""
    window_start = (dt.date.today() - dt.timedelta(days=args.days) + dt.timedelta(days=10)).isoformat()
    client = None

    for r in rk["rows"]:
        t = r["ticker"]
        df = load_prices(t)
        need_full = (
            df is None or df.empty
            or df["date"].iloc[-1] < prev                                   # 中間有缺口
            or (len(df) < args.min_bars and df["date"].iloc[0] <= window_start)   # 資料不足(非新上市)
        )
        if need_full:
            client = client or Polygon(cfg["polygon_min_interval_sec"])
            df = fetch_history(client, t, args.days)
            print(f"{t}: 全量回補 {len(df)} 根")
        else:
            bar = pd.DataFrame([{"date": date, "open": r["open"], "high": r["high"], "low": r["low"],
                                 "close": r["close"], "volume": r["volume"]}], columns=COLS)
            df = pd.concat([df, bar], ignore_index=True)
        if len(df):
            save_prices(t, df)
    print("歷史K線更新完成")


if __name__ == "__main__":
    main()
