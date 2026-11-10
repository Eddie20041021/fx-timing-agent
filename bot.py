"""Discord bot：換匯時機顧問。

    python3 bot.py

需要一個設定檔放 bot 的 token。建議放在「家目錄」的 fxbot.env，不要放在專案資料夾，
這樣上傳專案到 GitHub 時不會不小心把 token 一起傳上去：
    Mac：/Users/你的帳號/fxbot.env　　Windows：C:/Users/你的帳號/fxbot.env
內容：
    DISCORD_TOKEN=你的 bot token
    GUILD_ID=你的伺服器 ID           # 選填：填了指令會馬上出現，不填要等最多一小時
    CHANNEL_ID=要自動發建議的頻道 ID   # 選填：填了每週二、五早上 10 點自動發建議
"""

from __future__ import annotations

import asyncio
import datetime as dt
import io
import logging
import os
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks

from fxagent import chart, config, rates, replies

ROOT = Path(__file__).resolve().parent
TPE = ZoneInfo("Asia/Taipei")
log = logging.getLogger("fxbot")


# 放在家目錄、下載或桌面都可以（不要放在專案資料夾裡）；記事本常自動多加 .txt，所以也接受
ENV_DIRS = [Path.home(), Path.home() / "Downloads", Path.home() / "Desktop",
            Path.home() / "OneDrive" / "Desktop", Path.home() / "OneDrive" / "桌面"]
ENV_FILES = [d / n for d in ENV_DIRS for n in ("fxbot.env", "fxbot.env.txt")] + [ROOT / ".env"]


TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{20,}")


def load_env() -> None:
    """讀設定檔（不另外裝套件）。已經設定的環境變數優先。"""
    # 指定的檔名之外，家目錄／下載／桌面裡任何叫 fxbot… 的檔案（例如 fxbot.txt）也讀
    extra = [p for d in ENV_DIRS if d.exists() for p in sorted(d.glob("fxbot*"))
             if p.is_file() and "example" not in p.name and p not in ENV_FILES]
    for path in ENV_FILES + extra:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            if "DISCORD_TOKEN" not in os.environ or not os.environ["DISCORD_TOKEN"]:
                # 沒照格式寫也沒關係：只要這行裡有長得像 Discord token 的字串就拿來用
                m = TOKEN_RE.search(line)
                if m:
                    os.environ["DISCORD_TOKEN"] = m.group(0)


load_env()
TOKEN = os.environ.get("DISCORD_TOKEN", "")
GUILD_ID = int(os.environ.get("GUILD_ID", "0") or 0)
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0") or 0)

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

_last_update = 0.0


async def fresh_rates():
    """回答前先試著從台銀補最新匯率（10 分鐘內只抓一次）；抓不到就用本地資料。"""
    global _last_update
    if time.time() - _last_update > 600:
        try:
            n = await asyncio.to_thread(rates.update)
            log.info("更新匯率：新增 %d 天", n)
        except Exception as e:  # 網路或台銀出問題時不影響回答
            log.warning("更新匯率失敗，改用本地資料：%s", e)
        _last_update = time.time()
    return rates.load()


@tree.command(name="匯率", description="人民幣、日幣現在的台銀牌告，以及在近一年算貴還是便宜")
async def cmd_rates(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    df = await fresh_rates()
    await interaction.followup.send(replies.rates_text(df))


@tree.command(name="建議", description="這次人民幣該換幾成成台幣、日幣要不要買")
async def cmd_advice(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    df = await fresh_rates()
    text, _ = replies.advice_text(df)
    await interaction.followup.send(text)


@tree.command(name="走勢", description="畫出最近的匯率走勢")
@app_commands.rename(cur="幣別", days="天數")
@app_commands.describe(cur="要看哪個幣別", days="看最近幾天（30～730，預設 180）")
@app_commands.choices(cur=[app_commands.Choice(name="人民幣", value="CNY"),
                           app_commands.Choice(name="日幣", value="JPY")])
async def cmd_chart(interaction: discord.Interaction, cur: app_commands.Choice[str],
                    days: app_commands.Range[int, 30, 730] = 180):
    await interaction.response.defer(thinking=True)
    df = await fresh_rates()
    png = await asyncio.to_thread(chart.trend, df, cur.value, days)
    await interaction.followup.send(file=discord.File(io.BytesIO(png), filename=f"{cur.value.lower()}_{days}d.png"))


@tree.command(name="回測", description="過去兩年用不同做法換匯的比較")
async def cmd_backtest(interaction: discord.Interaction):
    await interaction.response.send_message(replies.backtest_text())


@tree.command(name="說明", description="這個 bot 能做什麼")
async def cmd_help(interaction: discord.Interaction):
    await interaction.response.send_message(replies.HELP)


@tasks.loop(time=dt.time(hour=10, minute=0, tzinfo=TPE))
async def scheduled_advice():
    """每週二、週五早上 10 點（台灣時間）自動發建議。"""
    if dt.datetime.now(TPE).weekday() not in config.DECISION_WEEKDAYS:
        return
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        log.warning("找不到頻道 %s，這次沒有發送", CHANNEL_ID)
        return
    df = await fresh_rates()
    text, _ = replies.advice_text(df)
    await channel.send(text)


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
    else:
        synced = await tree.sync()
    log.info("已登入 %s，同步 %d 個指令", client.user, len(synced))
    if CHANNEL_ID and not scheduled_advice.is_running():
        scheduled_advice.start()
        log.info("自動建議：每週二、五 10:00 發到頻道 %s", CHANNEL_ID)


@client.event
async def on_message(message: discord.Message):
    # 第 1 層：被 @ 的時候回說明；第 3 層會改成讀新聞與紀錄來回答問題
    if message.author.bot or message.mention_everyone or not client.user.mentioned_in(message):
        return
    await message.reply(replies.HELP + "\n\n（直接打字問問題的功能還在做，目前請用上面的指令）")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not TOKEN:
        found = sorted(str(p) for d in ENV_DIRS if d.exists() for p in d.glob("*fxbot*"))
        hint = (f"\n找到這些名字有 fxbot 的檔案：{found}" if found
                else "\n家目錄、下載、桌面都沒有名字有 fxbot 的檔案")
        tried = [str(p) for p in ENV_FILES if p.exists()] + found
        if tried:
            hint += ("\n檔案有讀到，但裡面找不到 token。請確認貼的是 Discord 開發者頁面 Bot 分頁按 Reset Token 後"
                     "複製的那一長串（中間有兩個點），不是 APPLICATION ID 或其他密碼")
        raise SystemExit(f"找不到 DISCORD_TOKEN：請建立 {ENV_FILES[0]}，內容寫 DISCORD_TOKEN=你的 token{hint}")
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
