"""bot 每個指令要回的文字。跟 Discord 無關的部分都放這裡，方便測試。"""

from __future__ import annotations

import json

import pandas as pd

from . import advice, config


def rates_text(df: pd.DataFrame) -> str:
    adv = advice.make(df)
    lines = [f"**現在匯率**（台銀牌告，資料日期 {adv['data_date']}）", ""]
    for cur, it in adv["items"].items():
        p = config.PAIRS[cur]
        f = lambda v: advice.fmt_price(cur, v)  # noqa: E731
        lines += [
            f"**{p['name']}**　{advice.price_label(cur)} = {f(it['price'])} 台幣（近一個月 {it['change_1m']:+.1f}%）",
            f"近一年範圍 {f(it['year_low'])} ～ {f(it['year_high'])}，{p['action']}的划算程度 {it['score']:.0f}／100（{it['level']}）",
            "",
        ]
    lines.append("划算程度＝近一年有幾 % 的日子比現在差。用 `/建議` 看這次該換多少。")
    return "\n".join(lines)


def advice_text(df: pd.DataFrame, log: bool = True) -> tuple[str, list[str]]:
    """產生建議並跑規則檢查。檢查沒過就不發建議，改回報錯誤（第 1 層理論上不會發生）。"""
    adv = advice.make(df)
    errors = advice.check(adv)
    if log:
        advice.save_log(adv, errors)
    if errors:
        return "⚠️ 建議沒有通過規則檢查，這次不發送：\n" + "\n".join("・" + e for e in errors), errors
    return advice.to_message(adv), errors


def backtest_text() -> str:
    path = config.REPORT_DIR / "backtest.json"
    if not path.exists():
        return "還沒有回測結果，請先執行 `python3 scripts/run_backtest.py`。"
    s = json.loads(path.read_text(encoding="utf-8"))
    c, j = s["pairs"]["CNY"], s["pairs"]["JPY"]
    return "\n".join([
        f"**回測**（{s['start']} ～ {s['end']}，每月入帳 1 萬人民幣、撥 1 萬台幣買日幣）",
        "",
        "**人民幣換台幣**（1 人民幣平均換到幾元台幣，越高越好）",
        f"A 收到就換 {c['A']['avg']:.4f}｜B 每週分批 {c['B']['avg']:.4f}｜C 看位置 {c['C']['avg']:.4f}",
        f"C 比 B 每 1 萬人民幣差 {c['C']['vs_B']:+,.0f} 台幣，其中只是「晚點換」就有 {c['E']['vs_B']:+,.0f}（對照組 E）",
        "",
        "**台幣買日幣**（1 萬日幣平均花幾元台幣，越低越好）",
        f"A 收到就換 {j['A']['avg']:,.1f}｜B 每週分批 {j['B']['avg']:,.1f}｜C 看位置 {j['C']['avg']:,.1f}",
        f"C 比 B 每 1 萬日幣省 {-j['C']['vs_B']:,.1f} 台幣，但有 {j['C']['leftover']:,.0f} 台幣預算等不到便宜時機沒花",
        "",
        "完整說明見 reports/backtest.md。",
    ])


HELP = "\n".join([
    "**換匯時機顧問**　我會告訴你人民幣、日幣現在在近一年算貴還是便宜。",
    "",
    "`/匯率`　現在的牌告與划算程度",
    "`/建議`　這次人民幣該換幾成成台幣、日幣要不要買",
    "`/走勢`　畫出最近的匯率走勢",
    "`/回測`　過去兩年用不同做法換匯的比較",
    "",
    "每週二、週五早上 10 點會自動發一次建議。",
    "以上建議僅供參考。",
])
