@echo off
REM ============================================================
REM  kepu-quiz : stop the API server.
REM  Finds whatever is listening on port 8000 and kills it.
REM  Keep this file pure ASCII.
REM ============================================================
setlocal
set "FOUND="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  set "FOUND=1"
  echo   stopping PID %%a
  taskkill /PID %%a /F >nul 2>&1
)
if not defined FOUND (
  echo   nothing is listening on port 8000
) else (
  echo   done.
)
ping -n 3 127.0.0.1 >nul
endlocal
