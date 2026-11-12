@echo off
REM ============================================================
REM  kepu-quiz : start the server for access from a phone.
REM
REM  Binds 0.0.0.0 instead of 127.0.0.1 so other devices on the
REM  same Wi-Fi can reach it. The console prints the LAN address.
REM
REM  Note: Windows Firewall may ask for permission the first time.
REM  Allow it on private networks only.
REM
REM  Keep this file pure ASCII.
REM ============================================================
setlocal
set "PYTHONPATH=E:\dev\.kepu-tools\backend-deps"
set "PYEXE=E:\dev\Python314\python.exe"
set "APPDIR=E:\dev\kepu-quiz\backend"

cd /d "%APPDIR%"

echo.
echo   kepu-quiz  (LAN mode)
echo   ---------------------
echo   Local addresses on this machine:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=* delims= " %%b in ("%%a") do echo     http://%%b:8000/app/
)
echo.
echo   On your phone, open the address above that starts with 192.168 or 10.
echo   Both devices must be on the same Wi-Fi.
echo.
echo   Close this window to stop the server.
echo.

"%PYEXE%" -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo Server stopped.
pause
endlocal
