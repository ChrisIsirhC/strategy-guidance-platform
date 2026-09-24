@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_strategy_platform.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
