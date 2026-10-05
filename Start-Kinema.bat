@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    echo Не найдена среда Python. Выполните установку по README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "scripts\launch.py" %*
if errorlevel 1 pause
