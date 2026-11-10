"""所有可以調整的數字都放在這裡。改規則改這個檔，不要把數字寫死在其他地方。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "bot_rates.csv"
LOG_DIR = ROOT / "logs"
REPORT_DIR = ROOT / "reports"

# 近一年 ≈ 250 個營業日
LOOKBACK_DAYS = 250

# 每週固定判斷的日子：週二、週五（Python weekday：週一 = 0）
DECISION_WEEKDAYS = (1, 4)

# 兩種操作，各自用哪個牌告價格
#   人民幣換台幣：銀行跟你「買」人民幣 → 本行即期買入，越高越好
#   台幣買日幣：銀行「賣」日幣給你 → 本行即期賣出，越低越好
PAIRS = {
    "CNY": {
        "name": "人民幣",
        "action": "換成台幣",
        "price_col": "CNY_spot_buy",
        "good_when": "high",
        "unit": 1,          # 顯示：1 人民幣 = ? 台幣
        "fmt": "{:.3f}",
    },
    "JPY": {
        "name": "日幣",
        "action": "用台幣買",
        "price_col": "JPY_spot_sell",
        "good_when": "low",
        "unit": 10000,      # 顯示：1 萬日幣 = ? 台幣
        "fmt": "{:,.0f}",
    },
}

# 基礎比例：依「現在落在近一年的哪個位置」決定這次動用多少
# (百分位下限, 比例)，由上往下找第一個符合的
#   人民幣：比例 = 目前手上人民幣的幾成換成台幣
#   日幣：  比例 = 目前累積的買日幣預算用掉幾成
RATIO_TABLE = {
    "CNY": [(80, 0.25), (60, 0.15), (40, 0.10), (20, 0.05), (0, 0.0)],
    # 日幣看的是「便宜程度」= 100 − 百分位
    "JPY": [(80, 0.50), (60, 0.25), (0, 0.0)],
}

# 硬規則（程式檢查，AI 之後也不能違反）
MAX_RATIO = {"CNY": 0.25, "JPY": 0.50}   # 單次最多動用的比例
MAX_HOLD_DAYS = 90                      # 人民幣入帳後最多放幾天，到期一定要換（回測假設）

# 回測假設：每月第一個營業日入帳 1 萬人民幣；每月撥 1 萬台幣當買日幣預算
MONTHLY_CNY_INCOME = 10_000
MONTHLY_JPY_BUDGET_TWD = 10_000
BACKTEST_START = "2024-12-01"   # 資料從 2023-12 開始，前 250 天用來算百分位
