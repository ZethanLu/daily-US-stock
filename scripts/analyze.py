"""步驟3:前20名、新進榜(對比前一日)、在榜天數、±門檻劇烈波動名單。"""
import argparse

from common import DATA, latest_ranking, load_config, ranking_files, read_json, write_json


def streak(ticker, history, k):
    """history:由新到舊的 [(日期, 前k名集合)];回傳連續在榜天數(含今日)。"""
    n = 0
    for _, s in history:
        if ticker not in s:
            break
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=None)
    ap.add_argument("--move-threshold", type=float, default=None)
    args = ap.parse_args()
    cfg = load_config()
    k = args.top_n or cfg["top_n_analysis"]
    thr = args.move_threshold or cfg["move_threshold_pct"]

    date, path = latest_ranking()
    today = read_json(path)
    files = [f for f in ranking_files() if f.stem <= date]
    prev = read_json(files[-2]) if len(files) >= 2 else None
    prev_rank = {r["ticker"]: r["rank"] for r in prev["rows"]} if prev else {}

    hist = {k_: [(f.stem, {r["ticker"] for r in read_json(f)["rows"] if r["rank"] <= k_})
                 for f in reversed(files)] for k_ in (k, len(today["rows"]))}
    rows = []
    for r in today["rows"]:
        t = r["ticker"]
        rows.append({**r,
                     "prev_rank": prev_rank.get(t),
                     "streak_top50": streak(t, hist[len(today["rows"])], len(today["rows"])),
                     "streak_top20": streak(t, hist[k], k)})

    top = [r for r in rows if r["rank"] <= k]
    prev_top = {t for t, rk in prev_rank.items() if rk <= k}
    new_top = [r["ticker"] for r in top if prev and r["ticker"] not in prev_top]
    new_50 = [r["ticker"] for r in rows if prev and r["prev_rank"] is None]
    dropped = sorted(prev_top - {r["ticker"] for r in top}) if prev else []
    movers = [{"ticker": r["ticker"], "rank": r["rank"], "change_pct": r["change_pct"],
               "dollar_volume": r["dollar_volume"]}
              for r in top if r["change_pct"] is not None and abs(r["change_pct"]) >= thr]
    movers.sort(key=lambda m: -abs(m["change_pct"]))

    write_json(DATA / "analysis" / f"{date}.json", {
        "date": date, "prev_date": prev["date"] if prev else None, "top_n": k, "threshold": thr,
        "has_prev": bool(prev), "top50": rows, "top20": top,
        "new_top20": new_top, "new_top50": new_50, "dropped_top20": dropped, "big_movers": movers,
    })
    print(f"{date}:新進前{k} {new_top};±{thr}% 波動 {[m['ticker'] for m in movers]}")


if __name__ == "__main__":
    main()
