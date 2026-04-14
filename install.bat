@echo off
setlocal
title SF Express Tracker - Install

echo ============================================================
echo   SF Express Tracker - Install
echo ============================================================
echo.

echo [1/3] Checking Python...
echo print(1) > "%TEMP%\sftest.py"
set PY=
python "%TEMP%\sftest.py" >nul 2>nul && set PY=python
if not defined PY (
    py "%TEMP%\sftest.py" >nul 2>nul && set PY=py
)
del "%TEMP%\sftest.py" >nul 2>nul

if defined PY (
    echo       Found: %PY%
    goto :pkgs
)

echo       Python not found. Downloading...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\pysetup.exe'"
if not exist "%TEMP%\pysetup.exe" (
    echo [ERROR] Download failed.
    echo         Please download from: https://www.python.org/downloads/
    echo         Check Add Python to PATH during install!
    pause
    exit /b 1
)
echo       Starting installer - Check Add Python to PATH!
"%TEMP%\pysetup.exe" InstallAllUsers=0 PrependPath=1 Include_pip=1
del "%TEMP%\pysetup.exe" >nul 2>nul
echo.
echo       Done! Close this window and run install.bat again.
pause
exit /b 0

:pkgs
echo.
echo [2/3] Installing packages...
%PY% -m pip install --upgrade pip >nul 2>nul
%PY% -m pip install playwright winotify opencv-python-headless numpy requests
if %errorlevel% neq 0 (
    echo [ERROR] Package install failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Installing Chromium...
%PY% -m playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Chromium install failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Install complete!
echo   1. Edit waybills.txt - add waybill numbers
echo   2. Double-click start.bat to start tracking
echo ============================================================
echo.
pause