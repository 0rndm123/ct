@echo off
setlocal
pushd "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cot_ingest.download weekly --lookback-days 56 %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found. Activate your conda environment or install Python.
        popd
        exit /b 1
    )
    python -m cot_ingest.download weekly --lookback-days 56 %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
