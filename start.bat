@echo off
title SF Express Tracker

echo print(1) > "%TEMP%\sftest.py"
set PY=
python "%TEMP%\sftest.py" >nul 2>nul && set PY=python
if not defined PY (
    py "%TEMP%\sftest.py" >nul 2>nul && set PY=py
)
del "%TEMP%\sftest.py" >nul 2>nul

if not defined PY (
    echo [ERROR] Python not found. Please run install.bat first.
    pause
    exit /b 1
)

cd /d "%~dp0"
%PY% -X utf8 sf_tracker.py

:confirm_exit
echo.
set /p QUIT=Are you sure you want to close? (Y/N): 
if /i "%QUIT%"=="N" goto confirm_exit
if /i "%QUIT%"=="n" goto confirm_exit
if /i "%QUIT%"=="Y" exit /b 0
if /i "%QUIT%"=="y" exit /b 0
goto confirm_exit