@echo off
title SF Express Tracker

REM Disable X (close) button to prevent accidental closing
REM Use Ctrl+C to stop the program
powershell -Command "$w=Add-Type -MemberDefinition '[DllImport(\"user32.dll\")]public static extern IntPtr GetSystemMenu(IntPtr h,bool r);[DllImport(\"user32.dll\")]public static extern bool DeleteMenu(IntPtr h,uint p,uint f);' -Name W -Namespace W -PassThru;$h=(Get-Process -Id $PID).MainWindowHandle;$m=$w::GetSystemMenu($h,$false);$w::DeleteMenu($m,0xF060,0)" >nul 2>nul

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

echo.
echo Program stopped. Press any key to close window...
pause >nul