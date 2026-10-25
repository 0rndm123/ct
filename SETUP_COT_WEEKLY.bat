@echo off
setlocal EnableExtensions
REM Run once from an interactive PowerShell window after INSTALL_COT.bat --existing.
REM Stores cot_loader password protected by Windows DPAPI for the current user.
REM Registers weekly task for Tuesday 09:00 local PC time (only while logged in).
pushd "%~dp0"
if errorlevel 1 exit /b 1
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_cot_weekly.ps1" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
