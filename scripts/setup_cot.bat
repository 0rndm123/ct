@echo off
setlocal
pushd "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python virtual environment missing. Run: py -3 -m venv .venv
  popd
  exit /b 1
)
REM Interactive admin and role passwords. Does not create/drop the database.
".venv\Scripts\python.exe" scripts\setup_cot.py %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
