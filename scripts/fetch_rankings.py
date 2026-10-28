"""步驟1:抓取前一美股交易日全市場資料,計算成交金額,輸出前 N 名。"""
import argparse
import datetime as dt
import re

from common import (DATA, Polygon, dollar_volume, get_meta, grouped, load_config,
                    last_session_candidate, previous_grouped, read_json, select_top,
                    set_output, write_json)


def pct(a, b):
    return round((a / b - 1) * 100, 2) if b else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    n = args.top or cfg["top_n"]
    client = Polygon(cfg["polygon_min_interval_sec"])

    target = last_session_candidate()
    out = DATA / "rankings" / f"{target}.json"
    if out.exists() and not args.force:
        print(f"{target} 已有排行檔,略過")
        return set_output("skipped", "true")

    g = grouped(client, target)
    if not g:
        print(f"{target} 無資料(休市或資料尚未提供),略過")
        return set_output("skipped", "true")
    prev_date, pg = previous_grouped(client, target)

    meta = read_json(DATA / "meta.json", {})
    tickers = select_top(client, g, n, cfg, meta)

    rows = []
    for i, t in enumerate(tickers, 1):
        b, m = g[t], meta[t]
        pc = pg.get(t, {}).get("c")
        mcap = m["shares"] * b["c"] if m.get("shares") else m.get("market_cap")
        rows.append({
            "rank": i, "ticker": t, "name": m["name"], "type": m["type"], "exchange": m.get("exchange"),
            "close": b["c"], "prev_close": pc, "change_pct": pct(b["c"], pc),
            "open": b["o"], "high": b["h"], "low": b["l"], "volume": b["v"],
            "dollar_volume": round(dollar_volume(b)), "market_cap": round(mcap) if mcap else None,
        })

    proxies = {}
    for t in cfg["market_proxies"]:
        b, pc = g.get(t), pg.get(t, {}).get("c")
        if b and pc:
            proxies[t] = {"close": b["c"], "change_pct": pct(b["c"], pc), "dollar_volume": round(dollar_volume(b))}

    adv = dec = flat = 0
    for t, b in g.items():
        pc = pg.get(t, {}).get("c")
        if pc and re.fullmatch(r"[A-Z]{1,5}", t) and b["c"] >= 1 and b["v"] >= 50000:
            adv, dec, flat = (adv + 1, dec, flat) if b["c"] > pc else (adv, dec + 1, flat) if b["c"] < pc else (adv, dec, flat + 1)

    write_json(out, {
        "date": str(target), "prev_date": prev_date,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "total_dollar_volume": round(sum(dollar_volume(b) for b in g.values())),
        "breadth": {"advancers": adv, "decliners": dec, "unchanged": flat, "note": "全市場(含ETF,價格≥1、量≥5萬股)"},
        "market_proxies": proxies, "rows": rows,
    })
    print(f"已輸出 {out.name}:{len(rows)} 檔")
    set_output("skipped", "false")


if __name__ == "__main__":
    main()
