@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%..\..\.."

set "MARP_VERSION=v4.3.1"
set "MARP_URL=https://github.com/marp-team/marp-cli/releases/download/%MARP_VERSION%/marp-cli-%MARP_VERSION%-win.zip"
rem --- Read template settings from config.toml ---
if not exist "config.toml" (
    echo [ERROR] config.toml not found.
    echo Please copy config\config.toml.template to config.toml and fill in your values.
    exit /b 1
)
for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "!SCRIPT_DIR!read_config.ps1" -Section template -Key name`) do set "TEMPLATE_NAME=%%V"
for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "!SCRIPT_DIR!read_config.ps1" -Section template -Key url`) do set "PPTX_URL=%%V"
if not defined TEMPLATE_NAME (
    echo [ERROR] Could not read template.name from config.toml.
    exit /b 1
)
set "PYTHON_VERSION=3.12.9"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"

echo.
echo ====== agent-ui Setup for Windows ======
echo.

if not exist "App\bin"        mkdir "App\bin"
if not exist "templates"      mkdir "templates"
if not exist "skills"         mkdir "skills"
if not exist "tmp"            mkdir "tmp"
if not exist ".gemini\skills" mkdir ".gemini\skills"

rem =======================================================
rem Step 1: marp CLI
rem =======================================================
if exist "App\bin\marp.exe" (
    echo [1/5] marp.exe already installed. Skipping.
) else (
    echo [1/5] Downloading marp CLI...
    curl -L --progress-bar -o "tmp\marp-win.zip" "%MARP_URL%"
    if errorlevel 1 ( echo [ERROR] marp download failed. & exit /b 1 )

    tar -xf "tmp\marp-win.zip" -C "App\bin" marp.exe >nul 2>&1
    if errorlevel 1 (
        powershell -NoProfile -Command ^
            "Expand-Archive -Path 'tmp\marp-win.zip' -DestinationPath 'tmp\_marp' -Force; ^
             Copy-Item 'tmp\_marp\marp.exe' 'App\bin\marp.exe'"
        if exist "tmp\_marp" rmdir /s /q "tmp\_marp"
    )
    del "tmp\marp-win.zip" >nul 2>&1

    if not exist "App\bin\marp.exe" (
        echo [ERROR] marp.exe not found after extraction.
        exit /b 1
    )
    echo [OK] marp.exe installed.
)

rem =======================================================
rem Step 2: PPTX template
rem =======================================================
if exist "templates\%TEMPLATE_NAME%" (
    echo [2/5] PPTX template already exists. Skipping.
) else (
    echo [2/5] Downloading PPTX template...
    curl -L --progress-bar -o "templates\%TEMPLATE_NAME%" "%PPTX_URL%"
    if errorlevel 1 (
        echo [WARN] Template download failed. Continuing without it.
    ) else (
        echo [OK] Template downloaded.
    )
)

rem =======================================================
rem Step 3: Build and install skills
rem =======================================================
echo [3/5] Building and installing skill packages...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-skills.ps1"
if errorlevel 1 ( echo [ERROR] Skill build failed. & exit /b 1 )

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-skills.ps1"
if errorlevel 1 ( echo [ERROR] Skill install failed. & exit /b 1 )
echo [OK] Skills installed.

rem =======================================================
rem Step 4: Python check / embedded install
rem =======================================================
echo [4/5] Checking Python...
set "PYTHON_CMD="
set "USE_EMBEDDED=0"

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 -c "import sys" >nul 2>&1
    if not errorlevel 1 ( set "PYTHON_CMD=python3" & goto :python_ready )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 ( set "PYTHON_CMD=python" & goto :python_ready )
)

if exist "App\python\python.exe" (
    echo [INFO] Using previously installed embedded Python.
    set "PYTHON_CMD=App\python\python.exe"
    set "USE_EMBEDDED=1"
    goto :python_ready
)

echo [INFO] Python not found. Installing embedded Python to App\python\...
curl -L --progress-bar -o "tmp\python-embed.zip" "%PYTHON_EMBED_URL%"
if errorlevel 1 ( echo [ERROR] Python download failed. & exit /b 1 )

if not exist "App\python" mkdir "App\python"
powershell -NoProfile -Command ^
    "Expand-Archive -Path 'tmp\python-embed.zip' -DestinationPath 'App\python' -Force"
del "tmp\python-embed.zip" >nul 2>&1
set "PYTHON_CMD=App\python\python.exe"
set "USE_EMBEDDED=1"
echo [OK] Embedded Python installed to App\python\

:python_ready
echo [OK] Python: %PYTHON_CMD%

rem =======================================================
rem Step 5: Python venv
rem =======================================================
if exist "venv\Scripts\activate.bat" (
    echo [5/5] venv already exists. Skipping.
) else if "%USE_EMBEDDED%"=="1" (
    echo [5/5] Embedded Python: setting up virtual environment...
    rem Enable site-packages (required for pip and virtualenv)
    for %%F in ("App\python\python3*._pth") do (
        powershell -NoProfile -Command "(Get-Content '%%~F') -replace '#import site', 'import site' | Set-Content '%%~F'"
    )
    rem Bootstrap pip if not already present
    if not exist "App\python\Scripts\pip.exe" (
        echo   Bootstrapping pip...
        curl -L -s -o "tmp\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
        if errorlevel 1 (
            echo [WARN] pip bootstrap download failed. Some features may not work.
            mkdir "venv" 2>nul
            goto :setup_done
        )
        "App\python\python.exe" "tmp\get-pip.py" --no-warn-script-location -q --no-cache-dir
        del "tmp\get-pip.py" >nul 2>&1
    )
    rem Use virtualenv to create a proper venv (embedded Python does not support python -m venv)
    "App\python\python.exe" -m pip install -q --disable-pip-version-check --no-cache-dir virtualenv
    "App\python\python.exe" -m virtualenv venv -q
    if errorlevel 1 (
        echo [WARN] venv creation failed. Creating marker directory.
        mkdir "venv" 2>nul
        goto :setup_done
    )
    rem Install all packages into the venv
    echo   Installing packages...
    venv\Scripts\python.exe -m pip install -q --disable-pip-version-check --no-cache-dir ^
        -r python\scripts\automation\requirements.txt ^
        google-auth google-auth-oauthlib google-api-python-client ^
        python-pptx markitdown pywin32
    if errorlevel 1 (
        echo [WARN] Package install failed. Some features may not work.
    ) else (
        echo [OK] venv ready.
    )
) else (
    echo [5/5] Creating Python virtual environment...
    "%PYTHON_CMD%" -m venv venv
    if errorlevel 1 (
        echo [WARN] venv creation failed. Creating marker directory.
        mkdir "venv" 2>nul
    ) else (
        echo   Installing packages...
        venv\Scripts\python.exe -m pip install -q --disable-pip-version-check --no-cache-dir ^
            -r python\scripts\automation\requirements.txt ^
            google-auth google-auth-oauthlib google-api-python-client ^
            python-pptx markitdown pywin32
        if errorlevel 1 (
            echo [WARN] Package install failed. Some features may not work.
        ) else (
            echo [OK] venv ready.
        )
    )
)

:setup_done
echo.
echo ====== Setup completed successfully! ======
echo.
exit /b 0
