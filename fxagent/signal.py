"""「現在划不划算」：純程式計算，不交給 AI。

划算程度（score，0–100）＝ 近一年（前 250 個營業日）裡，有幾 % 的日子比現在差：
    人民幣換台幣：有幾 % 的日子匯率比現在低  → 現在換越划算
    台幣買日幣：  有幾 % 的日子日幣比現在貴  → 現在買越划算
例如人民幣 score = 90，就是「現在比近一年 90% 的日子都高」。
"""

from __future__ import annotations

import pandas as pd

from . import config


def score(cur: str, series: pd.Series, asof=None, lookback: int | None = None) -> float:
    """只用 asof（含）以前的資料，避免前視偏誤。"""
    lookback = lookback or config.LOOKBACK_DAYS
    s = series.dropna()
    if asof is not None:
        s = s[s.index <= pd.Timestamp(asof)]
    window = s.tail(lookback + 1)
    if len(window) < lookback // 2:
        raise ValueError(f"資料不足：只有 {len(window)} 天，至少要 {lookback // 2} 天")
    now, past = window.iloc[-1], window.iloc[:-1]
    worse = past < now if config.PAIRS[cur]["good_when"] == "high" else past > now
    return float(worse.mean() * 100)


def base_ratio(cur: str, sc: float) -> float:
    for lower, ratio in config.RATIO_TABLE[cur]:
        if sc >= lower:
            return ratio
    return 0.0


def level(sc: float) -> str:
    if sc >= 80:
        return "很划算"
    if sc >= 60:
        return "偏划算"
    if sc >= 40:
        return "普通"
    if sc >= 20:
        return "偏不划算"
    return "不划算"
