@echo off
setlocal
pushd "%~dp0.."
REM Existing PostgreSQL database COT + prompt for role passwords + load local JSON.
REM This batch NEVER creates or drops a database and never saves passwords.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\setup_and_load.py %*
) else (
    python scripts\setup_and_load.py %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
