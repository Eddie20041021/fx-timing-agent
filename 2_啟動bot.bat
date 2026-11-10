@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Discord bot... (close this window to stop the bot)
py -V:3.13 bot.py
pause
