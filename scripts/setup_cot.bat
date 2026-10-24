@echo off
setlocal
pushd "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\setup_cot.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found. Activate your conda environment or install Python.
        popd
        exit /b 1
    )
    python scripts\setup_cot.py %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
