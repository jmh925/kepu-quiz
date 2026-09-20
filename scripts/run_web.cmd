@echo off
REM ============================================================
REM  kepu-quiz : start the server and open the student web app
REM
REM  Use this when you just want to click around locally.
REM  Use scripts\share.cmd instead if other people need access.
REM
REM  NOTE: keep this file pure ASCII (see scripts\share.cmd header).
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "PY=%KEPU_PYTHON%"
if "%PY%"=="" set "PY=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%ROOT%\backend"
echo [kepu] starting server ...
echo [kepu] student  http://127.0.0.1:8000/app/
echo [kepu] admin    http://127.0.0.1:8000/admin/
echo [kepu] docs     http://127.0.0.1:8000/docs
echo.
start "" http://127.0.0.1:8000/app/
"%PY%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
