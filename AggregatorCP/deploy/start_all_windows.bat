@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "TC_ROOT=%SCRIPT_DIR%.."

if "%TC_USE_UNIFIED_SERVICE%"=="" set "TC_USE_UNIFIED_SERVICE=1"
if "%TC_RUN_BRIDGE_SERVICE%"=="" set "TC_RUN_BRIDGE_SERVICE=1"
if "%TC_RUN_LEGACY_STACK%"=="" set "TC_RUN_LEGACY_STACK=0"

echo TC_USE_UNIFIED_SERVICE=%TC_USE_UNIFIED_SERVICE%
echo TC_RUN_BRIDGE_SERVICE=%TC_RUN_BRIDGE_SERVICE%
echo TC_RUN_LEGACY_STACK=%TC_RUN_LEGACY_STACK%

if "%TC_RUN_BRIDGE_SERVICE%"=="1" (
  echo Starting bridge service window...
  start "TravelerCompanion Bridge Service" /D "%SCRIPT_DIR%" cmd /k call start_bridge_service.bat
)

if "%TC_USE_UNIFIED_SERVICE%"=="1" (
  echo Starting unified companion service window...
  start "TravelerCompanion Unified Service" /D "%SCRIPT_DIR%" cmd /k call start_companion_service.bat
)

echo.
echo Launch sequence completed.
echo Bridge + unified service are started by default.
echo Set TC_RUN_BRIDGE_SERVICE=0 to skip bridge startup.
exit /b 0
