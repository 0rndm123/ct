@echo off
setlocal
pushd "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m cot_ingest.download verify %*
) else (
    python -m cot_ingest.download verify %*
)
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
