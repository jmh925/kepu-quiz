@echo off
REM ============================================================
REM  kepu-quiz : one-click start + open the browser
REM
REM  Double-click this file. It will:
REM    1. start the API server in a minimized window
REM    2. wait until the port answers
REM    3. open the student app in the default browser
REM
REM  The URL carries ?v=20261112 on purpose: the browser treats it
REM  as a new address, so a previously cached (old) page cannot be
REM  shown again.
REM
REM  NOTE on the health check: no pipe characters anywhere.
REM  A caret-escaped pipe inside a quoted PowerShell -Command is not
REM  unescaped by cmd.exe, so PowerShell receives a literal "^|" and
REM  the whole check always fails. That is why the first version of
REM  this script always timed out. Keep it pipe-free.
REM
REM  Keep this file pure ASCII.
REM ============================================================
setlocal
set "PYTHONPATH=E:\dev\.kepu-tools\backend-deps"
set "PYEXE=E:\dev\Python314\python.exe"
set "APPDIR=E:\dev\kepu-quiz\backend"
set "URL=http://127.0.0.1:8000/app/?v=20261112"
set "ADM=http://127.0.0.1:8000/admin/?v=20261112"

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

echo.
echo   [1/3] checking whether the server is already up ...
call :probe
if not errorlevel 1 (
  echo         already running.
  goto open
)

echo   [2/3] starting the server ...
cd /d "%APPDIR%"
start "kepu-quiz server" /min "%PYEXE%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo         waiting for it to come up ...
set /a tries=0
:wait
set /a tries+=1
ping -n 2 127.0.0.1 >nul
call :probe
if not errorlevel 1 goto open
if %tries% GEQ 25 goto failed
goto wait

:open
echo   [3/3] server is up, opening the browser ...
echo.
echo         student  %URL%
echo         admin    %ADM%    (admin / admin123)
echo.
echo   The server runs in the minimized window titled "kepu-quiz server".
echo   Close that window to stop it.
echo.
start "" "%URL%"
ping -n 4 127.0.0.1 >nul
exit /b 0

:failed
echo.
echo   ERROR: the server did not answer within about 50 seconds.
echo   Open the minimized window titled "kepu-quiz server" and read the error,
echo   or run this in PowerShell to see it directly:
echo.
echo     cd /d %APPDIR%
echo     set PYTHONPATH=E:\dev\.kepu-tools\backend-deps
echo     "%PYEXE%" -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
pause
exit /b 1

REM ---- health probe: exit code 0 when /api/v1/health answers 200 ----
:probe
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/v1/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; exit 1" >nul 2>&1
exit /b %errorlevel%
