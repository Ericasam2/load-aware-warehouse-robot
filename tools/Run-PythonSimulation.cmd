@echo off
setlocal
cd /d "%~dp0.."
set "SIM_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%SIM_PYTHON%" (
  "%SIM_PYTHON%" -m warehouse_planning.animation --show %*
) else (
  python -m warehouse_planning.animation --show %*
)
if errorlevel 1 pause
