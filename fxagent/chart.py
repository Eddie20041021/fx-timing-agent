"""畫圖：匯率走勢（bot 的 /走勢）與回測交易點（報告用）。"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

# Mac、Windows、Linux 常見的中文字型，依序找第一個有的
plt.rcParams["font.sans-serif"] = ["PingFang TC", "Heiti TC", "Microsoft JhengHei", "Noto Sans CJK TC",
                                   "Noto Sans CJK JP", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

RED, GREY, INK = "#c8102e", "#9a9a9a", "#222222"


def _ylabel(cur):
    return "1 人民幣換幾元台幣（本行即期買入）" if cur == "CNY" else "1 萬日幣要幾元台幣（本行即期賣出）"


def trend(df: pd.DataFrame, cur: str, days: int = 180) -> bytes:
    """最近 days 天（日曆天）的走勢，加上近一年的 20%／80% 位置線。"""
    p = config.PAIRS[cur]
    s = df[p["price_col"]] * p["unit"]
    year = s.tail(config.LOOKBACK_DAYS)
    show = s[s.index >= s.index[-1] - pd.Timedelta(days=days)]
    lo, hi = year.quantile(0.2), year.quantile(0.8)

    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    ax.plot(show.index, show.values, color=INK, lw=1.6)
    ax.axhline(hi, color=RED if cur == "CNY" else GREY, ls="--", lw=1)
    ax.axhline(lo, color=GREY if cur == "CNY" else RED, ls="--", lw=1)
    good, bad = ("近一年高檔（換台幣划算）", "近一年低檔") if cur == "CNY" else ("近一年高檔", "近一年低檔（買日幣划算）")
    box = dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1)
    ax.text(show.index[0], hi, " " + good, va="bottom", fontsize=9, color=RED if cur == "CNY" else GREY, bbox=box)
    ax.text(show.index[0], lo, " " + bad, va="top", fontsize=9, color=GREY if cur == "CNY" else RED, bbox=box)
    last = show.iloc[-1]
    ax.scatter([show.index[-1]], [last], color=RED, zorder=3)
    ax.annotate(p["fmt"].format(last), (show.index[-1], last), textcoords="offset points", xytext=(-6, 8),
                ha="right", fontsize=10, color=RED)
    ax.set_title(f"{p['name']}近 {days} 天走勢（台銀牌告）", fontsize=12)
    ax.set_ylabel(_ylabel(cur), fontsize=9)
    ax.grid(alpha=0.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def trades(df: pd.DataFrame, cur: str, result, start=config.BACKTEST_START) -> bytes:
    """回測期間的匯率，圓點是 C 每次動用的時間點，點越大代表動用越多。"""
    p = config.PAIRS[cur]
    s = (df[p["price_col"]] * p["unit"])[df.index >= pd.Timestamp(start)]
    fig, ax = plt.subplots(figsize=(9, 4), dpi=130)
    ax.plot(s.index, s.values, color=GREY, lw=1.2)
    xs = [pd.Timestamp(t[0]) for t in result.trades]
    ys = [t[3] * p["unit"] for t in result.trades]
    amounts = [t[2] for t in result.trades]
    m = max(amounts) if amounts else 1
    colors = [INK if ("強制" in t[1] or "結算" in t[1]) else RED for t in result.trades]
    ax.scatter(xs, ys, s=[10 + 140 * a / m for a in amounts], color=colors, alpha=0.75, zorder=3)
    what = "換成台幣" if cur == "CNY" else "買日幣"
    ax.set_title(f"C 只看位置：什麼時候{what}（紅點越大＝動用越多；黑點＝強制或期末結算）", fontsize=11)
    ax.set_ylabel(_ylabel(cur), fontsize=9)
    ax.grid(alpha=0.25)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
