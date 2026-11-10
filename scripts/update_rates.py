"""從台銀補最新匯率到 data/bot_rates.csv。

    python3 scripts/update_rates.py          # 補這個月和上個月
    python3 scripts/update_rates.py 6        # 補最近 6 個月
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fxagent import rates  # noqa: E402

if __name__ == "__main__":
    back = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = rates.update(months_back=back)
    df = rates.load()
    print(f"新增 {n} 天；資料範圍 {df.index[0]:%Y-%m-%d} ～ {df.index[-1]:%Y-%m-%d}，共 {len(df)} 天")
