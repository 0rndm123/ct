@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    popd
    exit /b 1
)
".venv\Scripts\python.exe" -m cot_ingest.cli verify
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
