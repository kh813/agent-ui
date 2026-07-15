@echo off
rem Pre-launch bootstrap for agent-ui (Windows), run automatically via
rem agent_config.json's pre_launch_command before every agy session start.
rem Creates the venv and builds skills on first run; keeps skills up to date
rem on every subsequent run.
rem
rem Invoked non-interactively (agent-ui captures stdout/stderr, no console),
rem so this must never `pause` for a keypress.
cd /d "%~dp0"

rem If venv\ doesn't exist yet, run the full Windows setup first. setup.bat
rem is a self-contained batch/PowerShell script that needs no pre-existing
rem Python -- it downloads an embedded Python + virtualenv itself if the
rem system has none -- which is exactly what solves the chicken-and-egg
rem problem of needing Python to run setup.py below in the first place.
if not exist "venv\" (
    call "%~dp0python\scripts\setup\setup.bat"
    if errorlevel 1 goto :setup_failed
)

if exist "venv\Scripts\python.exe" (
    set "PYEXE=venv\Scripts\python.exe"
) else (
    rem venv setup didn't produce a usable interpreter (or was already in
    rem this half-finished state from a previous failed run) -- fall back to
    rem system Python. Windows can have a "python" App Execution Alias stub
    rem even when Python is NOT installed: running it just opens the
    rem Microsoft Store and returns, instead of failing outright. `where
    rem python` alone would be fooled by this stub, so check that
    rem `python --version` actually prints "Python 3...".
    python --version 2>nul | findstr /r "^Python 3" >nul
    if errorlevel 1 goto :no_python
    set "PYEXE=python"
)

echo Checking configuration...
"%PYEXE%" python\scripts\setup\setup.py config

echo Updating skills...
"%PYEXE%" python\scripts\setup\setup.py skills rebuild
echo Ready.
exit /b %errorlevel%

:setup_failed
echo.
echo [ERROR] セットアップに失敗しました。ネットワーク接続を確認してから、もう一度実行してください。
echo [ERROR] Setup failed. Check your network connection, then try again.
echo.
exit /b 1

:no_python
echo.
echo [ERROR] Python が見つかりませんでした。Python をインストールしてから、もう一度実行してください。
echo [ERROR] Python was not found. Please install Python, then try again.
echo.
exit /b 1
