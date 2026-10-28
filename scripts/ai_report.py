"""步驟5:Gemini 盤面/新進榜/波動分析 → 報告 Markdown + data/latest.json。AI 失敗時降級為純數據報告。"""
import datetime as dt
import json
import os
import re
import time

import requests

from common import DATA, REPORTS, Polygon, latest_ranking, load_config, read_json, write_json

DISCLAIMER = "本報告由程式與 AI 自動產生,僅供資訊參考,不構成投資建議,內容可能延遲、不完整或有誤。"


def money(x):
    if x is None:
        return "—"
    return f"{x / 1e12:.2f} 兆" if x >= 1e12 else f"{x / 1e8:.1f} 億"


def pct(x):
    return "—" if x is None else f"{x:+.2f}%"


def get_news(client, ticker, date, limit=5):
    since = (dt.date.fromisoformat(date) - dt.timedelta(days=3)).isoformat()
    try:
        j = client.get("/v2/reference/news", {"ticker": ticker, "published_utc.gte": since,
                                             "order": "desc", "sort": "published_utc", "limit": limit})
    except Exception as e:           # 新聞端點失敗不應中斷整個流程
        print(f"  {ticker} 新聞取得失敗:{e}")
        return []
    return [{"title": a.get("title"), "publisher": (a.get("publisher") or {}).get("name"),
             "url": a.get("article_url"), "published": a.get("published_utc"),
             "summary": (a.get("description") or "")[:200]} for a in (j or {}).get("results") or []]


def call_gemini(prompt, model):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("未設定 GEMINI_API_KEY,AI 未啟用")
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
    for i in range(3):
        try:
            r = requests.post(url, json=body, headers={"x-goog-api-key": key}, timeout=180)
            if r.status_code in (429, 500, 503):
                time.sleep(20 * (i + 1))
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip())
        except Exception as e:
            print(f"Gemini 失敗({i + 1}/3):{e}")
            time.sleep(5)
    return None


def build_prompt(date, rk, an, news, need_themes):
    top = [{k: r[k] for k in ("rank", "ticker", "name", "close", "change_pct", "dollar_volume", "prev_rank")}
           for r in an["top20"]]
    return f"""你是美股盤後分析師。請用繁體中文,針對美東 {date} 的收盤資料產出分析。
嚴格規則:
1. 只能引用下方提供的資料與新聞;資料沒有的數字、事件不得編造。
2. 漲跌原因若新聞未提及,寫「未找到明確原因」;屬於你的推論須標「(推測)」。
3. sources 只能填下方新聞提供的 url,沒有就給空陣列。
4. 基本面與產業地位可用你既有的知識概述,但不可給具體最新財報數字(除非新聞提供),並註明資訊可能過時。

【前20名】{json.dumps(top, ensure_ascii=False)}
【ETF代理(盤面)】{json.dumps(rk['market_proxies'], ensure_ascii=False)}
【漲跌家數】{json.dumps(rk['breadth'], ensure_ascii=False)}
【全市場成交金額】{rk['total_dollar_volume']}
【新進前20】{an['new_top20']}   【掉出前20】{an['dropped_top20']}
【±{an['threshold']}%波動】{json.dumps(an['big_movers'], ensure_ascii=False)}
【相關新聞】{json.dumps(news, ensure_ascii=False)}
【需要補上題材的代號】{need_themes}

只輸出 JSON,格式:
{{"headline":["30秒重點1","重點2","重點3"],
 "market_tone":"一句話盤面性格",
 "market_analysis":"3~6句:指數ETF代理表現、強弱族群、資金流向、利率/美元/油金(僅限有提供的資料)、漲跌家數",
 "new_entrants":[{{"ticker":"","why_volume":"成交值暴增原因","trend":"近期走勢","fundamentals":"基本面重點","watch":"後續追蹤","sources":[]}}],
 "movers":[{{"ticker":"","drivers":"驅動原因","scope":"個別|產業|大盤|不明","overreaction":"反應是否過度","watch":"觀察重點","sources":[]}}],
 "themes":{{"代號":"題材/族群(8字內)"}}}}
new_entrants 與 movers 必須涵蓋上方所列的所有代號;若為空則給空陣列。"""


def clean_sources(items, allowed):
    for it in items or []:
        it["sources"] = [u for u in it.get("sources", []) if u in allowed]
    return items or []


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def build_md(date, rk, an, sc, ai, news, themes):
    L = [f"# 美股盤後分析:{date}(美東收盤)", ""]
    if ai:
        L += ["## 30 秒重點", *[f"- {h}" for h in ai.get("headline", [])], ""]
    else:
        L += ["> AI 未啟用或本次呼叫失敗,以下僅含程式計算的數據。", ""]

    L += ["## 1. 成交值前 20 名", md_table(
        ["#", "代碼", "名稱", "收盤", "漲跌幅", "成交金額(美元)", "昨日名次", "題材"],
        [[r["rank"], r["ticker"], r["name"], f"{r['close']:.2f}", pct(r["change_pct"]), money(r["dollar_volume"]),
          r["prev_rank"] or "新進榜", themes.get(r["ticker"], "")] for r in an["top20"]]), ""]

    L += ["## 2. 整體盤面"]
    if ai:
        L += [f"**盤面性格:**{ai.get('market_tone', '')}", "", ai.get("market_analysis", ""), ""]
    L += [md_table(["ETF 代理", "收盤", "漲跌幅"],
                   [[t, f"{v['close']:.2f}", pct(v["change_pct"])] for t, v in rk["market_proxies"].items()]), "",
          f"漲跌家數:上漲 {rk['breadth']['advancers']} / 下跌 {rk['breadth']['decliners']}"
          f"({rk['breadth']['note']});全市場成交金額約 {money(rk['total_dollar_volume'])} 美元。", ""]

    L += [f"## 3. 新進前 {an['top_n']} 名公司"]
    if not an["has_prev"]:
        L += ["尚無前一日資料可比對。", ""]
    elif not an["new_top20"]:
        L += ["今日無新進公司。", ""]
    else:
        for e in (ai or {}).get("new_entrants", []) or [{"ticker": t} for t in an["new_top20"]]:
            L += [f"### {e['ticker']}"]
            if "why_volume" in e:
                L += [f"- **成交值暴增原因:**{e['why_volume']}", f"- **近期走勢:**{e.get('trend', '')}",
                      f"- **基本面:**{e.get('fundamentals', '')}", f"- **後續追蹤:**{e.get('watch', '')}"]
            L += [f"- 來源:[{n['publisher']}]({n['url']}) {n['title']}" for n in news.get(e["ticker"], [])[:3]] + [""]

    L += [f"## 4. 劇烈波動(±{an['threshold']}%)"]
    if not an["big_movers"]:
        L += [f"今日前 {an['top_n']} 名無 ±{an['threshold']}% 波動公司。", ""]
    else:
        L += [md_table(["代碼", "名次", "漲跌幅", "成交金額"],
                       [[m["ticker"], m["rank"], pct(m["change_pct"]), money(m["dollar_volume"])] for m in an["big_movers"]]), ""]
        for m in (ai or {}).get("movers", []) or []:
            L += [f"### {m['ticker']}", f"- **驅動原因:**{m.get('drivers', '')}({m.get('scope', '不明')}因素)",
                  f"- **反應是否過度:**{m.get('overreaction', '')}", f"- **觀察重點:**{m.get('watch', '')}"]
            L += [f"- 來源:{u}" for u in m.get("sources", [])] + [""]
        if not ai:
            for m in an["big_movers"]:
                L += [f"- {m['ticker']} 相關新聞:" + (";".join(f"[{n['title']}]({n['url']})" for n in news.get(m["ticker"], [])[:3]) or "無")]
            L += [""]

    L += ["## 5. 技術線型篩選",
          f"範圍:成交值前 {sc['universe']} 名。型態A=區間整理且量縮;型態B=週MACD多方、日MACD回檔。", ""]
    for key, label in (("pattern_a", "型態A"), ("pattern_b", "型態B")):
        L += [f"**{label}:** " + (("、".join(x["ticker"] for x in sc[key])) or "無")]
    L += [f"**同時符合A與B:** " + ("、".join(sc["both"]) or "無"), ""]
    if sc["near"]:
        L += ["接近名單(僅差一項):", *[f"- {n['ticker']}(型態{n['pattern']}):{n['reason']}" for n in sc["near"]], ""]
    if sc["insufficient"]:
        L += ["資料不足無法驗證:" + "、".join(sc["insufficient"]), ""]
    L += ["---", f"*{DISCLAIMER}*"]
    return "\n".join(L)


def main():
    cfg = load_config()
    date, path = latest_ranking()
    rk, an = read_json(path), read_json(DATA / "analysis" / f"{date}.json")
    sc = read_json(DATA / "screen" / f"{date}.json")
    client = Polygon(cfg["polygon_min_interval_sec"])

    focus = list(dict.fromkeys(an["new_top20"] + [m["ticker"] for m in an["big_movers"]]))[:12]
    news = {t: get_news(client, t, date) for t in focus}
    allowed = {n["url"] for v in news.values() for n in v if n.get("url")}

    themes = read_json(DATA / "themes.json", {})
    need = [r["ticker"] for r in an["top50"] if r["ticker"] not in themes]
    ai = call_gemini(build_prompt(date, rk, an, news, need), cfg["gemini_model"])
    if ai:
        themes.update({k: v for k, v in (ai.get("themes") or {}).items() if isinstance(v, str)})
        write_json(DATA / "themes.json", themes)
        clean_sources(ai.get("new_entrants"), allowed)
        clean_sources(ai.get("movers"), allowed)

    md = build_md(date, rk, an, sc, ai, news, themes)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{date}.md").write_text(md, encoding="utf-8")
    (REPORTS / "latest.md").write_text(md, encoding="utf-8")
    dates = sorted((p.stem for p in REPORTS.glob("2*.md")), reverse=True)
    write_json(REPORTS / "index.json", dates)

    rows = [{**r, "theme": themes.get(r["ticker"], ""), "is_new": an["has_prev"] and r["prev_rank"] is None}
            for r in an["top50"]]
    write_json(DATA / "latest.json", {
        "date": date, "prev_date": an["prev_date"], "generated_at": rk["generated_at"], "ai_enabled": bool(ai),
        "total_dollar_volume": rk["total_dollar_volume"], "breadth": rk["breadth"], "market_proxies": rk["market_proxies"],
        "headline": (ai or {}).get("headline", []), "market_tone": (ai or {}).get("market_tone", ""),
        "rows": rows, "new_top20": an["new_top20"], "big_movers": an["big_movers"], "threshold": an["threshold"],
        "screen": sc,
    })
    print(f"報告完成:reports/{date}.md(AI {'啟用' if ai else '未啟用'})")


if __name__ == "__main__":
    main()
