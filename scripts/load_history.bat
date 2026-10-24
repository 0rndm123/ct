@echo off
REM Historical import from YYYY-MM-DD JSON files, with no CFTC API call.
REM Download first with scripts\download_history.bat.
call "%~dp0import_history.bat" %*
exit /b %ERRORLEVEL%
