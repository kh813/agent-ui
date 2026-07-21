@echo off
rem Pre-launch bootstrap for agent-deck (Windows), run automatically via
rem agent_config.json's pre_launch_command before every agy session start.
rem Creates the venv and builds skills on first run; keeps skills up to date
rem on every subsequent run.
rem
rem Invoked non-interactively (agent-deck captures stdout/stderr, no console),
rem so this must never `pause` for a keypress.
rem
rem 2026-07-21: this file used to have raw Japanese `echo` lines and
rem multi-line parenthesized if/else blocks with a nested goto -- the exact
rem two bugs confirmed for real on a wrapping project's own copy of this
rem same file (see that project's admin docs / commit history for the full
rem incident writeup): cmd.exe reads a .bat file's own source bytes as
rem CP932 on Japanese Windows, and a UTF-8 non-ASCII byte can look like a
rem stray paren/metacharacter mid-scan; separately, a goto exiting a
rem multi-line ( ... ) block right before another one begins can desync
rem cmd.exe's own pre-read/tokenize pass. Fixed the same way: every
rem bilingual message now lives in its own file under messages\, printed
rem via `type` (a raw byte-forwarder) instead of a literal `echo` argument,
rem and every conditional uses single-line `if <cond> goto :label`
rem statements instead of a multi-line ( ... ) block. Do not reintroduce
rem either pattern without testing the FULL script on a real Windows
rem machine.
cd /d "%~dp0"
rem Tells setup.py's _prompt() helper to skip straight to an empty answer
rem instead of trying to detect non-interactivity itself -- confirmed for
rem real that relying on sys.stdin.isatty() alone still hung indefinitely
rem on a genuinely fresh Windows install, waiting forever at the email
rem prompt during first-time setup.
set "AGENT_DECK_NONINTERACTIVE=1"

rem If venv\ doesn't exist yet, run the full Windows setup first. setup.bat
rem is a self-contained batch/PowerShell script that needs no pre-existing
rem Python -- it downloads an embedded Python + virtualenv itself if the
rem system has none -- which is exactly what solves the chicken-and-egg
rem problem of needing Python to run setup.py below in the first place.
if exist "venv\" goto :venv_exists
call "%~dp0python\scripts\setup\setup.bat"
if errorlevel 1 goto :setup_failed

:venv_exists
if exist "venv\Scripts\python.exe" goto :use_venv_python
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
goto :python_check_done

:use_venv_python
set "PYEXE=venv\Scripts\python.exe"

:python_check_done
echo Checking configuration...
"%PYEXE%" python\scripts\setup\setup.py config

echo Updating skills...
"%PYEXE%" python\scripts\setup\setup.py skills rebuild
echo Ready.
exit /b %errorlevel%

:setup_failed
echo.
type "%~dp0messages\setup_failed.txt"
echo.
exit /b 1

:no_python
echo.
type "%~dp0messages\no_python.txt"
echo.
exit /b 1
