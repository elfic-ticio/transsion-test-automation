@echo off
title Transsion Test Automation - Servidor
cd /d "%~dp0"
echo ================================================
echo   Transsion Test Automation - Tecno / Infinix
echo   Iniciando servidor en http://localhost:5000
echo ================================================
if not exist logs mkdir logs
if not exist data mkdir data
if not exist screenshots mkdir screenshots
echo.
python app.py
pause
