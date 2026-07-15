@echo off
if exist "%~dp0..\..\..\venv\Scripts\python.exe" (
    set "PYTHON=%~dp0..\..\..\venv\Scripts\python.exe"
) else if exist "%~dp0..\..\..\App\python\python.exe" (
    set "PYTHON=%~dp0..\..\..\App\python\python.exe"
) else (
    echo [ERROR] Python not found. Please run setup first.
    exit /b 1
)
"%PYTHON%" "%~dp0automate.py" %*
