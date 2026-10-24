@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Create the virtual environment and install requirements first.
    popd
    exit /b 1
)
if not defined COT_DATABASE_URL (
    echo ERROR: COT_DATABASE_URL is not set.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m cot_ingest.cli history %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
