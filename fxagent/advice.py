"""產生建議，以及檢查建議有沒有違反規則。

第 1 層：建議完全由程式產生。
第 2 層：AI 讀新聞後會微調比例、改寫文字，但仍然要通過 check()，沒過就退回。
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from . import config, signal


def fmt_price(cur: str, price: float) -> str:
    p = config.PAIRS[cur]
    return p["fmt"].format(price * p["unit"])


def price_label(cur: str) -> str:
    return "1 人民幣" if cur == "CNY" else "1 萬日幣"


def make(df: pd.DataFrame, asof=None) -> dict:
    """用 asof（含）以前的資料產生兩個幣別的建議。"""
    data = df if asof is None else df[df.index <= pd.Timestamp(asof)]
    day = data.index[-1]
    out = {"data_date": day.strftime("%Y-%m-%d"), "made_at": dt.datetime.now().isoformat(timespec="seconds"), "items": {}}
    for cur, p in config.PAIRS.items():
        s = data[p["price_col"]]
        window = s.tail(config.LOOKBACK_DAYS)
        sc = signal.score(cur, s)
        ratio = signal.base_ratio(cur, sc)
        price = float(s.iloc[-1])
        prev30 = float(s.iloc[-22]) if len(s) >= 22 else float(s.iloc[0])  # 約一個月前（22 個營業日）
        item = {
            "price": price,
            "score": round(sc, 1),
            "level": signal.level(sc),
            "ratio": ratio,
            "year_low": float(window.min()),
            "year_high": float(window.max()),
            "change_1m": round((price / prev30 - 1) * 100, 2),
        }
        item["text"] = render(cur, item)
        out["items"][cur] = item
    return out


def render(cur: str, it: dict) -> str:
    """給家人看的一句話。數字一律從 it 來，不另外算。"""
    p = config.PAIRS[cur]
    price = fmt_price(cur, it["price"])
    high = p["good_when"] == "high"
    if it["score"] >= 100:
        pos = "創近一年新高" if high else "是近一年最便宜"
    elif it["score"] < 1:
        pos = "接近近一年最低" if high else "接近近一年最貴"
    else:
        pos = f"比近一年 {it['score']:.0f}% 的日子{'高' if high else '便宜'}"
    head = f"{p['name']}：{price_label(cur)} = {price} 台幣，{pos}（{it['level']}）"
    if it["ratio"] > 0:
        what = "手上人民幣" if cur == "CNY" else "買日幣預算"
        verb = "換成台幣" if cur == "CNY" else "拿去買日幣"
        return f"{head}→ 建議把{what}的 {it['ratio']:.0%} {verb}。"
    return f"{head}→ 建議先等，這次不{'換' if cur == 'CNY' else '買'}。"


def check(adv: dict) -> list[str]:
    """規則檢查：回傳違反的項目，空清單代表通過。

    這些規則用程式判斷，不問模型；第 2 層 AI 改過的建議也要過這一關。
    """
    errors = []
    for cur, it in adv["items"].items():
        name = config.PAIRS[cur]["name"]
        r = it["ratio"]
        if not 0 <= r <= config.MAX_RATIO[cur]:
            errors.append(f"{name}：比例 {r:.0%} 超出 0～{config.MAX_RATIO[cur]:.0%}")
        if cur == "JPY" and r > 0 and it["score"] < 60:
            errors.append(f"{name}：只有在偏划算以上（划算程度 ≥ 60）才能買，現在是 {it['score']:.0f}")
        text = it["text"]
        # 文字要跟決定一致
        if r > 0 and ("先等" in text or f"{r:.0%}" not in text):
            errors.append(f"{name}：決定動用 {r:.0%}，文字卻沒寫這個比例或寫了「先等」")
        if r == 0 and "先等" not in text:
            errors.append(f"{name}：決定不動，文字卻沒寫「先等」")
        # 文字裡的價格要對得上資料
        if fmt_price(cur, it["price"]) not in text:
            errors.append(f"{name}：文字裡的價格跟資料對不上（應該是 {fmt_price(cur, it['price'])}）")
        if ("新高" in text or "最便宜" in text) and it["score"] < 100:
            errors.append(f"{name}：文字說是近一年最好的價格，但資料不是")
        if ("最低" in text or "最貴" in text) and it["score"] >= 1:
            errors.append(f"{name}：文字說接近近一年最差的價格，但資料不是")
        for num in re.findall(r"(\d+)% 的日子", text):
            if abs(int(num) - it["score"]) > 1:
                errors.append(f"{name}：文字寫 {num}%，資料是 {it['score']:.0f}%")
    return errors


def to_message(adv: dict) -> str:
    lines = [f"**換匯建議**（台銀牌告，資料日期 {adv['data_date']}）", ""]
    for cur in config.PAIRS:
        lines.append("・" + adv["items"][cur]["text"])
    lines += ["", "以上依近一年匯率位置計算，僅供參考。"]
    return "\n".join(lines)


def save_log(adv: dict, errors: list[str], kind: str = "advice") -> str:
    config.LOG_DIR.mkdir(exist_ok=True)
    path = config.LOG_DIR / f"{kind}_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({**adv, "check_errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
