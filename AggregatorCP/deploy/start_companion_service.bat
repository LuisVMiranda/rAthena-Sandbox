@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "SERVICE_DIR=%SCRIPT_DIR%..\companion-service"
if "%TC_COMPANION_CONFIG%"=="" set "TC_COMPANION_CONFIG=%APPDATA%\TravelerCompanion\config.json"

if not exist "%SERVICE_DIR%\app.py" (
  echo Missing companion-service\app.py
  exit /b 1
)

where py >nul 2>&1
if "%ERRORLEVEL%"=="0" (
  py -m pip install -r "%SERVICE_DIR%\requirements.txt"
  py -m uvicorn app:app --app-dir "%SERVICE_DIR%" --host 127.0.0.1 --port 4310
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if "%ERRORLEVEL%"=="0" (
  python -m pip install -r "%SERVICE_DIR%\requirements.txt"
  python -m uvicorn app:app --app-dir "%SERVICE_DIR%" --host 127.0.0.1 --port 4310
  exit /b %ERRORLEVEL%
)

echo Python not found in PATH.
exit /b 1
