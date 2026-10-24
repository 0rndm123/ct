@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Create the virtual environment and install requirements first.
    popd
    exit /b 1
)
if "%COT_DATABASE_URL%"=="" (
    echo ERROR: COT_DATABASE_URL is not set.
    popd
    exit /b 1
)
REM Overlap 56 days to recover delayed runs. Date is the CFTC position date, not release date.
".venv\Scripts\python.exe" -m cot_ingest.cli weekly --lookback-days 56 %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
