@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."
set "PYTHON_BIN=%PYTHON_BIN%"
if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"

if "%TC_BRIDGE_SHARED_SECRET%"=="" (
  echo WARNING: TC_BRIDGE_SHARED_SECRET is not set.
  echo Set it before running for secure verification.
)

%PYTHON_BIN% -m pip install -r "%ROOT%\bridge-service\requirements.txt"
if errorlevel 1 (
  echo Failed to install bridge dependencies.
  pause
  exit /b 1
)

%PYTHON_BIN% -m uvicorn app:app --app-dir "%ROOT%\bridge-service" --host 127.0.0.1 --port 8099
