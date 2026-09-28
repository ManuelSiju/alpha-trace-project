@echo off
setlocal enabledelayedexpansion
REM Alpha-Tracer launcher (Windows). Provisions everything via uv, then runs the app.
REM No administrator rights required anywhere in this script.
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv ^(Python packaging tool^) not found — installing it for your user account only...
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo Could not install uv automatically.
        echo Install it manually, then re-run alpha.bat:
        echo   powershell -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        echo   ^(see https://docs.astral.sh/uv/getting-started/installation/ for other options^)
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>nul
    if errorlevel 1 (
        echo uv was installed but isn't on PATH in this shell.
        echo Open a new terminal ^(so it picks up the updated PATH^) and re-run alpha.bat.
        exit /b 1
    )
)

if not exist ".venv" (
    echo Creating virtual environment ^(.venv^) with Python 3.11 via uv...
    uv venv --python 3.11 .venv
    if errorlevel 1 exit /b 1
)

echo Installing dependencies...
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 exit /b 1

if not exist ".venv\.playwright_installed" (
    echo Installing Playwright's Chromium ^(one-time, optional — used only for LinkedIn scraping^)...
    ".venv\Scripts\python.exe" -m playwright install chromium
    if not errorlevel 1 (
        type nul > ".venv\.playwright_installed"
    ) else (
        echo Warning: Playwright Chromium install failed or was skipped. Alpha-Tracer will still run;
        echo this only affects the optional LinkedIn-scraping path.
    )
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo Note: 'ollama' was not found on PATH. Alpha-Tracer will still run using a
    echo deterministic fallback briefing, but for LLM-powered analysis, install it:
    echo   winget install Ollama.Ollama
    echo   ^(or download from https://ollama.com/download^)
    echo.
)

".venv\Scripts\python.exe" main.py %*
