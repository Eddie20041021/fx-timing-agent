@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -V:3.13 -m unittest discover tests -v
pause
