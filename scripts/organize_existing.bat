@echo off
setlocal
pushd "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cot_ingest.download migrate --start-year 2019 %*
) else (
    python -m cot_ingest.download migrate --start-year 2019 %*
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo ERROR: migration failed. Existing archive not deleted or moved.
    popd
    exit /b %RC%
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cot_ingest.download verify
) else (
    python -m cot_ingest.download verify
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
