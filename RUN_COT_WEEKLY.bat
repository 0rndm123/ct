@echo off
setlocal EnableExtensions
REM Execute from PowerShell or Task Scheduler (no password prompt).
REM OneDrive: D:\OD\OneDrive\Fin\data\COT\YYYY-MM-DD\<report>.json
REM PostgreSQL: COT/cot (account cot_loader).
REM Configure first: .\SETUP_COT_WEEKLY.bat
pushd "%~dp0"
if errorlevel 1 exit /b 1
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0scripts\run_cot_weekly.ps1" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
