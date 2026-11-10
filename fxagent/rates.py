"""台灣銀行牌告匯率：讀取本地資料、從台銀下載更新。

台銀每個幣別每個月一個 CSV：
    https://rate.bot.com.tw/xrt/flcsv/0/<YYYY-MM>/<幣別>
欄位：資料日期, 幣別, [本行買入] 匯率, 現金, 即期, 遠期…, [本行賣出] 匯率, 現金, 即期, 遠期…
台銀只保留大約三年的歷史資料，所以本地 CSV 要留著，只往後補。
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.request

import pandas as pd

from . import config

URL = "https://rate.bot.com.tw/xrt/flcsv/0/{month}/{cur}"
COLUMNS = ["CNY_spot_buy", "CNY_spot_sell", "CNY_cash_buy", "JPY_spot_buy", "JPY_spot_sell", "JPY_cash_sell"]


def load(path=config.DATA_FILE) -> pd.DataFrame:
    """讀本地匯率，index 是日期（由舊到新）。"""
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df[COLUMNS]


def parse_month_csv(text: str) -> dict[str, dict[str, float]]:
    """解析台銀單一幣別、單一月份的 CSV → {YYYY-MM-DD: {cash_buy, spot_buy, cash_sell, spot_sell}}"""
    out = {}
    for row in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if len(row) < 15 or not row[0].strip().isdigit():
            continue  # 標題列或空行
        d = row[0].strip()
        out[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = {
            "cash_buy": float(row[3]), "spot_buy": float(row[4]),
            "cash_sell": float(row[13]), "spot_sell": float(row[14]),
        }
    return out


def fetch_month(month: str, cur: str, timeout: int = 20) -> str:
    req = urllib.request.Request(URL.format(month=month, cur=cur), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")


def update(path=config.DATA_FILE, months_back: int = 1, today: dt.date | None = None) -> int:
    """下載這個月（和前 months_back 個月）的牌告，補進本地 CSV。回傳新增的天數。

    已經存在的日期會用台銀最新的數字覆蓋（當天盤中更新過的情況）。
    """
    today = today or dt.date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(months_back + 1):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12

    fresh: dict[str, dict[str, float]] = {}
    for mo in months:
        cny = parse_month_csv(fetch_month(mo, "CNY"))
        jpy = parse_month_csv(fetch_month(mo, "JPY"))
        for d in sorted(set(cny) & set(jpy)):
            a, b = cny[d], jpy[d]
            fresh[d] = {
                "CNY_spot_buy": a["spot_buy"], "CNY_spot_sell": a["spot_sell"], "CNY_cash_buy": a["cash_buy"],
                "JPY_spot_buy": b["spot_buy"], "JPY_spot_sell": b["spot_sell"], "JPY_cash_sell": b["cash_sell"],
            }

    df = load(path)
    before = len(df)
    for d, vals in fresh.items():
        df.loc[pd.Timestamp(d), COLUMNS] = [vals[c] for c in COLUMNS]
    df = df.sort_index()
    _save(df, path)
    return len(df) - before


def _save(df: pd.DataFrame, path) -> None:
    out = df.copy()
    out.index = out.index.strftime("%Y-%m-%d")
    out.index.name = "date"
    for c in COLUMNS:
        out[c] = out[c].map(lambda v: f"{v:.4f}" if c.startswith("JPY") else f"{v:.3f}")
    out.to_csv(path)
