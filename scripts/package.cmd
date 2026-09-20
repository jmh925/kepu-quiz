@echo off
REM ============================================================
REM  kepu-quiz : build the deliverable zip (Windows)
REM
REM  Output: dist\<chinese-name>_YYYYMMDD.zip
REM  (the Chinese name is produced by tools\package_release.py,
REM   NOT written in this file -- see the note below)
REM
REM  NOTE: keep this file pure ASCII (see scripts\share.cmd header).
REM  The zip is named in Chinese, and Chinese text inside a .cmd
REM  file is exactly what breaks cmd.exe parsing, so the whole
REM  packaging job lives in Python instead.
REM ============================================================
setlocal
set "ROOT=%~dp0.."
if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"
cd /d "%ROOT%"
"%KEPU_PYTHON%" -X utf8 tools\package_release.py %*
set "RC=%ERRORLEVEL%"
echo.
echo [kepu] done (exit code %RC%). Press any key to close.
pause >nul
endlocal
exit /b %RC%
