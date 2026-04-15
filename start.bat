@echo off
echo print(1) > "%TEMP%\sftest.py"
set PY=
python "%TEMP%\sftest.py" >nul 2>nul && set PY=pythonw
if not defined PY (
    py "%TEMP%\sftest.py" >nul 2>nul && set PY=pyw
)
del "%TEMP%\sftest.py" >nul 2>nul

if not defined PY (
    echo [ERROR] Python not found. Please run install.bat first.
    pause
    exit /b 1
)

cd /d "%~dp0"
start "" %PY% launcher.pyw