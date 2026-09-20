@echo off
REM ============================================================
REM  kepu-quiz : build the interactive browser demo of the
REM  WeChat mini program (Windows).
REM
REM  Why it exists: without WeChat DevTools you still want to
REM  click through the mini-program flow in a plain browser.
REM
REM  Prerequisite: the server running in another window
REM  (scripts\run_server.cmd), and Node.js on PATH.
REM
REM  NOTE: keep this file pure ASCII (see scripts\share.cmd header).
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "PY=%KEPU_PYTHON%"
if "%PY%"=="" set "PY=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%ROOT%"
echo [1/3] generating demo page ...
node tools\make_demo.js || goto :fail

echo [2/3] self-check and screenshots ...
"%PY%" -X utf8 tools\verify_demo.py

echo [3/3] opening demo page ...
start "" "%ROOT%\demo\index.html"
echo.
echo demo page : %ROOT%\demo\index.html
echo shots     : %ROOT%\demo\shots
goto :eof

:fail
echo [kepu] generation failed - check that Node.js is installed (node --version).
exit /b 1
endlocal
