"""回測：同一段期間、同樣的入帳、同一套規則，比較不同換匯做法。

    A 收到就換：每月入帳當天全部換（日幣：預算撥下來當天全部買）
    B 每週分批：把當月的錢平均分到當月每個週二、週五（主要對照組）
    C 只看位置：每個週二、週五依「划算程度」決定動用幾成（第 1 層）
    E 延後分批：不看匯率，只是把錢平均分到「跟 C 一樣久」的期間
       → 用來分辨 C 贏 B 是因為「看位置」，還是只是因為「晚一點換」剛好碰上趨勢
    D 位置＋AI 讀新聞：第 2 層完成後加入

防止前視偏誤：判斷日 t 的划算程度只用 t 的「前一個營業日」以前的資料算，成交用 t 當天的牌告。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config, signal

EPS = 1e-9


@dataclass
class Result:
    name: str
    cur: str
    foreign: float = 0.0     # 換掉（人民幣）或買到（日幣）的外幣
    twd: float = 0.0         # 拿到（人民幣）或花掉（日幣）的台幣
    trades: list = field(default_factory=list)
    hold_days: float = 0.0   # 錢從入帳到用掉的天數 × 金額（算平均持有天數用）
    leftover: float = 0.0    # 期末沒用掉的日幣預算（台幣）
    forced: float = 0.0      # 因為放太久被強制換掉的人民幣
    settled: float = 0.0     # 期末結算才換掉的人民幣

    @property
    def avg(self) -> float:
        """人民幣：平均 1 人民幣換到幾元台幣；日幣：平均 1 萬日幣花幾元台幣"""
        if self.foreign < EPS:
            return float("nan")
        return self.twd / self.foreign if self.cur == "CNY" else self.twd / self.foreign * 10000

    @property
    def avg_hold(self) -> float:
        used = self.foreign if self.cur == "CNY" else self.twd
        return self.hold_days / used if used > EPS else 0.0


def _days(df: pd.DataFrame, start, end):
    d = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
    days = list(d.index)
    income_days = list(d.groupby(d.index.to_period("M")).head(1).index)   # 每月第一個營業日
    decision_days = [t for t in days if t.weekday() in config.DECISION_WEEKDAYS]
    return days, income_days, decision_days


def scores_for(df: pd.DataFrame, cur: str, days) -> dict:
    """每個營業日 t → 用 t 前一個營業日以前的資料算的划算程度"""
    s = df[config.PAIRS[cur]["price_col"]]
    pos = {t: i for i, t in enumerate(s.index)}
    return {t: signal.score(cur, s.iloc[: pos[t]]) for t in days}


def _plan(income_days, decision_days, amount, window_days=None) -> dict:
    """把每筆入帳平均分到之後的判斷日。window_days=None：分到當月底；否則分到入帳後 window_days 天內。"""
    plan: dict = {}
    for t in income_days:
        if window_days is None:
            slots = [d for d in decision_days if d >= t and d.to_period("M") == t.to_period("M")]
        else:
            slots = [d for d in decision_days if t <= d < t + pd.Timedelta(days=window_days)]
        slots = slots or [t]
        for d in slots:
            plan.setdefault(d, []).append((t, amount / len(slots)))
    return plan


class _Book:
    """記帳：每筆錢什麼時候入帳、什麼時候用掉、用掉時的牌告"""

    def __init__(self, res: Result, price: pd.Series):
        self.r, self.price = res, price

    def use(self, t, amount, since, why):
        if amount <= EPS:
            return
        p = float(self.price[t])
        if self.r.cur == "CNY":
            self.r.foreign += amount
            self.r.twd += amount * p
        else:
            self.r.twd += amount
            self.r.foreign += amount / p
        self.r.hold_days += (t - since).days * amount
        self.r.trades.append((t.date(), why, round(amount, 2), p, since.date()))


def _run_planned(name, cur, price, days, plan) -> Result:
    r = Result(name, cur)
    book = _Book(r, price)
    for t in days:
        for since, amt in plan.get(t, []):
            book.use(t, amt, since, "分批" if name != "A" else "入帳")
    return r


def _run_signal(cur, price, days, income_days, decision_days, scores, amount) -> Result:
    """C：判斷日依划算程度動用手上（或預算）的幾成，先用最早入帳的錢。"""
    r = Result("C", cur)
    book = _Book(r, price)
    lots: list[list] = []          # [入帳日, 剩下的金額]
    incomes = set(income_days)
    decisions = set(decision_days)
    for t in days:
        if t in incomes:
            lots.append([t, float(amount)])
        if t in decisions:
            sc = scores[t]
            want = sum(a for _, a in lots) * signal.base_ratio(cur, sc)
            for lot in lots:
                take = min(lot[1], want)
                if take > EPS:
                    book.use(t, take, lot[0], f"划算程度 {sc:.0f}")
                    lot[1] -= take
                    want -= take
        if cur == "CNY":
            # 硬規則：人民幣放滿 MAX_HOLD_DAYS 天一定要換
            for lot in lots:
                if lot[1] > EPS and (t - lot[0]).days >= config.MAX_HOLD_DAYS:
                    book.use(t, lot[1], lot[0], f"放滿 {config.MAX_HOLD_DAYS} 天強制換")
                    r.forced += lot[1]
                    lot[1] = 0.0
        lots = [l for l in lots if l[1] > EPS]
    rest = sum(a for _, a in lots)
    if cur == "CNY":
        for lot in lots:      # 期末還沒換的，以最後一天的牌告換掉（另外標註）
            book.use(days[-1], lot[1], lot[0], "期末結算")
        r.settled = rest
    else:
        r.leftover = rest     # 日幣預算沒用完就留著，不強迫買
    return r


def run(df: pd.DataFrame, cur: str, start=config.BACKTEST_START, end=None) -> dict[str, Result]:
    end = end or df.index[-1]
    price = df[config.PAIRS[cur]["price_col"]]
    days, income_days, decision_days = _days(df, start, end)
    amount = config.MONTHLY_CNY_INCOME if cur == "CNY" else config.MONTHLY_JPY_BUDGET_TWD
    scores = scores_for(df, cur, days)

    out = {
        "A": _run_planned("A", cur, price, days, {t: [(t, amount)] for t in income_days}),
        "B": _run_planned("B", cur, price, days, _plan(income_days, decision_days, amount)),
        "C": _run_signal(cur, price, days, income_days, decision_days, scores, amount),
    }
    # E：跟 C 平均持有一樣久，但不看匯率（平均分配 → 平均延後 ≈ 期間的一半）
    window = max(7, round(out["C"].avg_hold * 2))
    out["E"] = _run_planned("E", cur, price, days, _plan(income_days, decision_days, amount, window))
    out["E"].window = window
    return out
