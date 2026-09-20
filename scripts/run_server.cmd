@echo off
REM ============================================================
REM  kepu-quiz : start the API server (Windows)
REM  Usage: double-click this file, or run scripts\run_server.cmd
REM
REM  Requires the dependencies first:
REM      pip install -r backend\requirements.txt
REM  If you copied them into backend\deps for an offline machine, the
REM  PYTHONPATH line below picks that folder up automatically.
REM
REM  Local URLs after start:
REM    http://127.0.0.1:8000/app/     student web app
REM    http://127.0.0.1:8000/admin/   admin console
REM    http://127.0.0.1:8000/docs     Swagger API docs
REM
REM  To let other people reach it, use scripts\share.cmd instead.
REM
REM  NOTE: keep this file pure ASCII (see scripts\share.cmd header).
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "BACKEND=%ROOT%\backend"

if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%BACKEND%"
echo [kepu] server   http://127.0.0.1:8000
echo [kepu] docs     http://127.0.0.1:8000/docs
echo [kepu] admin    http://127.0.0.1:8000/admin/
echo [kepu] student  http://127.0.0.1:8000/app/
echo.
"%KEPU_PYTHON%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
endlocal
