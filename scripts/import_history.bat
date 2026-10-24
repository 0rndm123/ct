@echo off
setlocal
pushd "%~dp0.."
if not defined COT_DATABASE_URL (
    echo ERROR: COT_DATABASE_URL must use cot_loader for database COT.
    popd
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cot_ingest.import_weekly --start-year 2019 %*
) else (
    python -m cot_ingest.import_weekly --start-year 2019 %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
