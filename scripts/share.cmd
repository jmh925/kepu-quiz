@echo off
REM ============================================================
REM  kepu-quiz : one-click public demo (Windows)
REM
REM  Starts the API server, opens a free Cloudflare quick tunnel,
REM  waits until the public URL really answers, then prints the
REM  student / admin URLs and the admin password.
REM
REM  Usage:  double-click this file, or:
REM            scripts\share.cmd                 (server + tunnel)
REM            scripts\share.cmd --no-tunnel     (local only)
REM            scripts\share.cmd --tunnel-only   (server already up)
REM
REM  Press Ctrl+C to stop. The tunnel is always closed; the API
REM  server is stopped only if this script started it.
REM
REM  NOTE FOR MAINTAINERS -- KEEP THIS FILE PURE ASCII.
REM  cmd.exe reads .cmd files using the OEM code page (GBK on
REM  Chinese Windows). UTF-8 Chinese bytes get re-paired, which
REM  swallows the following ASCII character -- including quote
REM  marks -- and cmd then tries to run fragments of the text as
REM  commands. All Chinese output lives in tools\share.py, which
REM  is UTF-8 safe. tools\check_cmd_encoding.py guards this rule.
REM ============================================================
setlocal
set "ROOT=%~dp0.."

if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%ROOT%"
title kepu-quiz public demo  (Ctrl+C to stop)
"%KEPU_PYTHON%" -X utf8 tools\share.py %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo [kepu] script exited with code %RC%
echo [kepu] finished - press any key to close this window.
pause >nul
endlocal
exit /b %RC%
