@echo off
REM ============================================================
REM  kepu-quiz : start the API server in a standalone window
REM
REM  Double-click this file to run the system. It only serves
REM  to this machine:  http://127.0.0.1:8000/app/
REM
REM  Why a separate launcher: the dependencies live OUTSIDE the
REM  repo (E:\dev\.kepu-tools\backend-deps), so PYTHONPATH has to
REM  be set before uvicorn starts. Keeping that here means the
REM  user never has to type it.
REM
REM  NOTE: keep this file pure ASCII. Chinese text inside a .cmd
REM  breaks cmd.exe parsing on Chinese Windows (the UTF-8 bytes
REM  get re-paired as GBK and swallow the following ASCII byte,
REM  including quotes).
REM ============================================================
setlocal
set "PYTHONPATH=E:\dev\.kepu-tools\backend-deps"
set "PYEXE=E:\dev\Python314\python.exe"
set "APPDIR=E:\dev\kepu-quiz\backend"

if not exist "%PYEXE%" (
  echo ERROR: python not found at %PYEXE%
  pause
  exit /b 1
)
if not exist "%APPDIR%\app\main.py" (
  echo ERROR: app not found at %APPDIR%
  pause
  exit /b 1
)

cd /d "%APPDIR%"

echo.
echo   kepu-quiz
echo   ---------
echo   student  http://127.0.0.1:8000/app/
echo   admin    http://127.0.0.1:8000/admin/   (admin / admin123)
echo   api doc  http://127.0.0.1:8000/docs
echo.
echo   Close this window to stop the server.
echo.

"%PYEXE%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Server stopped.
pause
endlocal
