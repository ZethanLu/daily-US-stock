"""每週:以還原價格重抓歷史K線,修正股票分割/除權息造成的不連續。"""
import argparse
import datetime as dt

from common import (Polygon, fetch_history, load_config, ranking_files, read_json, save_prices)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=460)
    ap.add_argument("--active-days", type=int, default=30, help="只重整最近 N 天內入榜過的股票")
    args = ap.parse_args()
    cfg = load_config()
    cutoff = (dt.date.today() - dt.timedelta(days=args.active_days)).isoformat()
    tickers = set()
    for f in ranking_files():
        if f.stem >= cutoff:
            tickers |= {r["ticker"] for r in read_json(f)["rows"]}
    client = Polygon(cfg["polygon_min_interval_sec"])
    for i, t in enumerate(sorted(tickers), 1):
        df = fetch_history(client, t, args.days)
        if len(df):
            save_prices(t, df)
        print(f"[{i}/{len(tickers)}] {t}: {len(df)} 根")


if __name__ == "__main__":
    main()
