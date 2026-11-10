@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  [1/4] Install Python 3.13
echo  (If it asks "Install CPython now? [Y/n]", type n and press Enter)
echo ============================================
py install 3.13
echo.
echo ============================================
echo  [2/4] Install packages (pandas, matplotlib, discord.py)
echo ============================================
py -V:3.13 -m pip install -r requirements.txt
echo.
echo ============================================
echo  [3/4] Run tests (should end with OK)
echo ============================================
py -V:3.13 -m unittest discover tests
echo.
echo ============================================
echo  [4/4] Update rates and show today's advice
echo ============================================
py -V:3.13 scripts\advise.py
echo.
echo Done. Take a screenshot of this window for Claude.
pause
