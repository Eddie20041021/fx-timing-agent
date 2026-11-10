"""不用 Discord，直接在終端機看這次的建議（會先試著更新匯率）。

    python3 scripts/advise.py
    python3 scripts/advise.py --no-update     # 不連網，用現有資料
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxagent import rates, replies  # noqa: E402

if __name__ == "__main__":
    if "--no-update" not in sys.argv:
        try:
            rates.update()
        except Exception as e:
            print(f"（更新匯率失敗，改用現有資料：{e}）")
    df = rates.load()
    print(replies.rates_text(df))
    print()
    text, errors = replies.advice_text(df)
    print(text)
