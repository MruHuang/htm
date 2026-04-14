@echo off
title SF Express Tracker

echo print(1) > "%TEMP%\pytest.py"
set PY=
python "%TEMP%\pytest.py" >nul 2>nul && set PY=python
if not defined PY (
    py "%TEMP%\pytest.py" >nul 2>nul && set PY=py
)
del "%TEMP%\pytest.py" >nul 2>nul

if not defined PY (
    echo [ERROR] Python not found. Please run install.bat first.
    pause
    exit /b 1
)

cd /d "%~dp0"
%PY% -X utf8 sf_tracker.py
pause
