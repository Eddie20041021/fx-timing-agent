"""跑回測並產生報告：reports/backtest.md、reports/backtest.json、兩張交易點圖、交易明細 CSV。

    python3 scripts/run_backtest.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxagent import backtest, chart, config, rates  # noqa: E402

NAMES = {"A": "收到就換", "B": "每週分批", "C": "只看位置", "E": "延後分批（對照）"}


def main():
    df = rates.load()
    config.REPORT_DIR.mkdir(exist_ok=True)
    start, end = config.BACKTEST_START, df.index[-1].strftime("%Y-%m-%d")
    summary = {"start": start, "end": end, "lookback_days": config.LOOKBACK_DAYS,
               "max_hold_days": config.MAX_HOLD_DAYS, "pairs": {}}
    md = [
        "# 回測結果（第 1 層）",
        "",
        f"- 期間：{start} ～ {end}（台銀牌告，每日收盤）",
        f"- 假設：每月第一個營業日入帳 {config.MONTHLY_CNY_INCOME:,} 人民幣；每月撥 {config.MONTHLY_JPY_BUDGET_TWD:,} 台幣當買日幣預算",
        f"- 判斷日：每週二、週五；划算程度用「前一個營業日以前」的近 {config.LOOKBACK_DAYS} 個營業日計算（不偷看未來）",
        f"- 人民幣放滿 {config.MAX_HOLD_DAYS} 天一定要換；期末還沒換的以最後一天牌告結算",
        "- 由 `python3 scripts/run_backtest.py` 產生，數字不要手改",
        "",
    ]
    for cur in ("CNY", "JPY"):
        out = backtest.run(df, cur)
        b = out["B"].avg
        unit = "1 人民幣平均換到（台幣）" if cur == "CNY" else "1 萬日幣平均花費（台幣）"
        md += [f"## {config.PAIRS[cur]['name']}", "", f"| 做法 | {unit} | 跟 B 比 | 平均持有天數 | 交易次數 | 備註 |",
               "|---|---|---|---|---|---|"]
        summary["pairs"][cur] = {}
        for k in ("A", "B", "C", "E"):
            r = out[k]
            if cur == "CNY":
                diff = (r.avg - b) * 10000
                vs = "—" if k == "B" else f"{diff:+,.0f} 台幣／每 1 萬人民幣"
                note = []
                if r.forced:
                    note.append(f"強制換 {r.forced:,.0f}")
                if r.settled:
                    note.append(f"期末結算 {r.settled:,.0f}")
                avg = f"{r.avg:.4f}"
            else:
                diff = r.avg - b
                vs = "—" if k == "B" else f"{diff:+,.1f} 台幣／每 1 萬日幣"
                note = [f"預算剩 {r.leftover:,.0f} 台幣沒用（用掉 {r.twd / (r.twd + r.leftover):.0%}）"] if r.leftover else []
                avg = f"{r.avg:,.1f}"
            if k == "E":
                note.append(f"不看匯率，平均分到入帳後 {r.window} 天內")
            md.append(f"| {k} {NAMES[k]} | {avg} | {vs} | {r.avg_hold:.1f} | {len(r.trades)} | {'；'.join(note)} |")
            summary["pairs"][cur][k] = {"avg": r.avg, "vs_B": diff if k != "B" else 0.0, "avg_hold": r.avg_hold,
                                       "trades": len(r.trades), "forced": r.forced, "settled": r.settled,
                                       "leftover": r.leftover}
        md.append("")
        img = f"backtest_{cur.lower()}.png"
        (config.REPORT_DIR / img).write_bytes(chart.trades(df, cur, out["C"]))
        md += [f"![C 的交易點]({img})", ""]
        with open(config.REPORT_DIR / f"trades_{cur.lower()}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["做法", "日期", "原因", "金額", "牌告", "這筆錢的入帳日"])
            for k in ("A", "B", "C", "E"):
                for t in out[k].trades:
                    w.writerow([k, *t])

    c, j = summary["pairs"]["CNY"], summary["pairs"]["JPY"]
    md += [
        "## 怎麼讀",
        "",
        f"- 人民幣：C 比 B 每 1 萬人民幣多換到 {c['C']['vs_B']:+,.0f} 台幣；但 E（只是晚一點換、不看匯率）也多了 {c['E']['vs_B']:+,.0f}。",
        f"  所以 C 的優勢裡，真正來自「看位置」的只有 C − E ≈ {c['C']['vs_B'] - c['E']['vs_B']:+,.0f} 台幣，其他是因為這段期間人民幣整體是升值的，晚一點換本來就比較划算。",
        f"- 日幣：C 每 1 萬日幣比 B 省 {-j['C']['vs_B']:,.1f} 台幣，E 跟 B 幾乎一樣（{j['E']['vs_B']:+,.1f}），代表日幣這邊的差距主要來自「看位置」，不是延後。",
        f"  但 C 有 {j['C']['leftover']:,.0f} 台幣預算一直等不到便宜的時候，沒有花掉。",
        "- 兩年的資料只是一段行情，結果會隨期間改變；這也是第 2 層要加入新聞、第 3 層要實際執行累積紀錄的原因。",
    ]
    (config.REPORT_DIR / "backtest.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (config.REPORT_DIR / "backtest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
