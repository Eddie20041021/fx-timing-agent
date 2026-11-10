"""python3 -m unittest discover tests"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxagent import advice, backtest, config, rates, signal  # noqa: E402

SAMPLE = (
    "﻿資料日期,幣別,匯率,現金,即期,遠期10天,遠期30天,遠期60天,遠期90天,遠期120天,遠期150天,遠期180天,"
    "匯率,現金,即期,遠期10天,遠期30天,遠期60天,遠期90天,遠期120天,遠期150天,遠期180天\n"
    "20261030,CNY,本行買入,4.78500,4.85700,0,0,0,0,0,0,0,本行賣出,4.94700,4.90700,0,0,0,0,0,0,0\n"
)


class TestRates(unittest.TestCase):
    def test_parse(self):
        d = rates.parse_month_csv(SAMPLE)
        self.assertEqual(d["2026-10-30"], {"cash_buy": 4.785, "spot_buy": 4.857, "cash_sell": 4.947, "spot_sell": 4.907})

    def test_local_data(self):
        df = rates.load()
        self.assertTrue(df.index.is_monotonic_increasing)
        self.assertFalse(df.index.duplicated().any())
        self.assertFalse(df.isna().any().any())
        # 買入一定比賣出便宜
        self.assertTrue((df.CNY_spot_buy < df.CNY_spot_sell).all())
        self.assertTrue((df.JPY_spot_buy < df.JPY_spot_sell).all())


class TestSignal(unittest.TestCase):
    def setUp(self):
        self.df = rates.load()

    def test_no_lookahead(self):
        """改掉 asof 之後的資料，asof 那天的划算程度不能變"""
        s = self.df["CNY_spot_buy"].copy()
        asof = s.index[400]
        before = signal.score("CNY", s, asof)
        s.iloc[401:] = 99.0
        self.assertEqual(before, signal.score("CNY", s, asof))

    def test_direction(self):
        s = self.df["JPY_spot_sell"].copy()
        s.iloc[-1] = s.tail(251).min() - 0.001          # 日幣比近一年都便宜
        self.assertEqual(signal.score("JPY", s), 100.0)
        c = self.df["CNY_spot_buy"].copy()
        c.iloc[-1] = c.tail(251).min() - 0.001          # 人民幣比近一年都低
        self.assertEqual(signal.score("CNY", c), 0.0)

    def test_ratio_table(self):
        self.assertEqual(signal.base_ratio("CNY", 95), 0.25)
        self.assertEqual(signal.base_ratio("CNY", 10), 0.0)
        self.assertEqual(signal.base_ratio("JPY", 59.9), 0.0)
        self.assertEqual(signal.base_ratio("JPY", 85), 0.50)


class TestAdviceCheck(unittest.TestCase):
    def setUp(self):
        self.adv = advice.make(rates.load())

    def test_passes(self):
        self.assertEqual(advice.check(self.adv), [])

    def test_catches_bad_ratio(self):
        a = copy.deepcopy(self.adv)
        a["items"]["CNY"]["ratio"] = 0.6
        self.assertTrue(any("超出" in e for e in advice.check(a)))

    def test_catches_text_mismatch(self):
        a = copy.deepcopy(self.adv)
        a["items"]["CNY"]["text"] = a["items"]["CNY"]["text"].replace("建議把手上人民幣的 25% 換成台幣", "建議先等")
        self.assertTrue(any("文字" in e for e in advice.check(a)))

    def test_catches_wrong_price(self):
        a = copy.deepcopy(self.adv)
        a["items"]["JPY"]["text"] = a["items"]["JPY"]["text"].replace("2,101", "2,011")
        self.assertTrue(any("價格" in e for e in advice.check(a)))

    def test_jpy_only_when_cheap(self):
        a = copy.deepcopy(self.adv)
        a["items"]["JPY"]["ratio"] = 0.25
        a["items"]["JPY"]["text"] = "日幣：1 萬日幣 = 2,101 台幣 → 建議把買日幣預算的 25% 拿去買日幣。"
        self.assertTrue(any("偏划算以上" in e for e in advice.check(a)))


class TestBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = rates.load()
        cls.cny = backtest.run(cls.df, "CNY")
        cls.jpy = backtest.run(cls.df, "JPY")

    def test_money_is_conserved(self):
        months = len({t.to_period("M") for t in self.df.index[self.df.index >= config.BACKTEST_START]})
        total_cny = months * config.MONTHLY_CNY_INCOME
        for r in self.cny.values():
            self.assertAlmostEqual(r.foreign, total_cny, places=3, msg=r.name)
        total_twd = months * config.MONTHLY_JPY_BUDGET_TWD
        for r in self.jpy.values():
            self.assertAlmostEqual(r.twd + r.leftover, total_twd, places=3, msg=r.name)

    def test_hold_limit(self):
        """人民幣最多放 MAX_HOLD_DAYS 天（遇到假日最多再晚幾天）；期末結算不算"""
        held = [(t[0] - t[4]).days for t in self.cny["C"].trades if t[1] != "期末結算"]
        self.assertLessEqual(max(held), config.MAX_HOLD_DAYS + 4)

    def test_backtest_no_lookahead(self):
        """把最後 60 天的匯率改掉，之前的交易不能變"""
        df2 = self.df.copy()
        cut = df2.index[-60]
        df2.loc[df2.index >= cut, "CNY_spot_buy"] = 9.9
        c2 = backtest.run(df2, "CNY")["C"]
        before = [t for t in self.cny["C"].trades if str(t[0]) < str(cut.date())]
        before2 = [t for t in c2.trades if str(t[0]) < str(cut.date())]
        self.assertEqual(before, before2)


if __name__ == "__main__":
    unittest.main()
