@echo off
REM ============================================================
REM  kepu-quiz : backend API smoke test (Windows)
REM
REM  Prerequisite: the server must already be running in another
REM  window (scripts\run_server.cmd).
REM
REM  Output: backend\tests\smoke_report.md
REM          (the measured data used by chapter 6 of the thesis)
REM
REM  NOTE: keep this file pure ASCII (see scripts\share.cmd header).
REM ============================================================
setlocal
set "ROOT=%~dp0.."
if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"
cd /d "%ROOT%\backend"
"%KEPU_PYTHON%" -X utf8 tests\smoke_test.py
endlocal
