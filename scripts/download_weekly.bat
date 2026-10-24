@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python virtual environment missing. Run: py -3 -m venv .venv
  popd
  exit /b 1
)
REM No database credentials required. Creates a new immutable weekly source snapshot.
".venv\Scripts\python.exe" -m cot_ingest.download weekly --lookback-days 56 %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
