"""首次建置:為成交值前 N 名(及歷來入榜者)回補約 300+ 交易日的日K。"""
import argparse
import datetime as dt

from common import (DATA, Polygon, grouped, last_session_candidate, load_config, load_prices,
                    ranking_files, read_json, save_prices, select_top, fetch_history)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=460)
    ap.add_argument("--universe-size", type=int, default=100)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    client = Polygon(cfg["polygon_min_interval_sec"])

    d, g = last_session_candidate(), {}
    for _ in range(7):                       # 往前找最近有資料的交易日
        g = grouped(client, d)
        if g:
            break
        d -= dt.timedelta(days=1)
    if not g:
        raise SystemExit("找不到最近的交易日資料")
    meta = read_json(DATA / "meta.json", {})
    universe = set(select_top(client, g, args.universe_size, cfg, meta))
    for f in ranking_files():                # 併入歷來入榜者
        universe |= {r["ticker"] for r in read_json(f)["rows"]}
    print(f"回補名單 {len(universe)} 檔(以 {d} 為基準)")

    for i, t in enumerate(sorted(universe), 1):
        df = load_prices(t)
        if df is not None and len(df) >= 280 and not args.force:
            print(f"[{i}/{len(universe)}] {t} 已有 {len(df)} 根,略過")
            continue
        df = fetch_history(client, t, args.days)
        if len(df):
            save_prices(t, df)
        print(f"[{i}/{len(universe)}] {t}: {len(df)} 根")


if __name__ == "__main__":
    main()
