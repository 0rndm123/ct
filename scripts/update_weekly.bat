@echo off
REM Official CFTC download -> OneDrive position-date files -> PostgreSQL COT.
REM Only after setup and manual validation of the initial history.
call "%~dp0download_weekly.bat"
if errorlevel 1 (
    echo ERROR: Weekly CFTC download failed; PostgreSQL unchanged.
    exit /b 1
)
call "%~dp0import_weekly.bat"
exit /b %ERRORLEVEL%
