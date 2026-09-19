@echo off
REM ============================================================
REM  一键打包交付物（Windows）
REM  产物：dist\科普知识闯关小程序_交付物_YYYYMMDD.zip
REM  包含：源码、文档、论文与插图、测试报告、脚本；不含运行期数据库与缓存
REM ============================================================
setlocal enabledelayedexpansion
set "ROOT=%~dp0.."
cd /d "%ROOT%"

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "D=%%a%%b%%c"
set "STAMP=%D%"
set "DIST=%ROOT%\dist"
set "PKG=%DIST%\科普知识闯关小程序_交付物_%STAMP%"
if not exist "%PKG%" mkdir "%PKG%"

echo [1/4] 复制源码与文档 ...
robocopy "%ROOT%\backend"  "%PKG%\backend"  /E /NFL /NDL /NJH /NJS /XD __pycache__ deps\__pycache__ /XF *.pyc *.log >nul
robocopy "%ROOT%\frontend" "%PKG%\frontend" /E /NFL /NDL /NJH /NJS /XF *.log >nul
robocopy "%ROOT%\admin"    "%PKG%\admin"    /E /NFL /NDL /NJH /NJS >nul
robocopy "%ROOT%\docs"     "%PKG%\docs"     /E /NFL /NDL /NJH /NJS >nul
robocopy "%ROOT%\scripts"  "%PKG%\scripts"  /E /NFL /NDL /NJH /NJS >nul
robocopy "%ROOT%\tools"    "%PKG%\tools"    /E /NFL /NDL /NJH /NJS /XF *.pyc >nul
copy /y "%ROOT%\README.md"  "%PKG%\README.md"  >nul
copy /y "%ROOT%\LICENSE"    "%PKG%\LICENSE"    >nul
copy /y "%ROOT%\.gitignore" "%PKG%\.gitignore" >nul

echo [2/4] 清理运行期产物 ...
if exist "%PKG%\backend\data" del /q "%PKG%\backend\data\*.db*" 2>nul
del /q "%PKG%\backend\.env" 2>nul
del /q "%PKG%\backend\tests\_*.log" 2>nul

echo [3/4] 压缩 ...
powershell -NoProfile -Command "Compress-Archive -Path '%PKG%' -DestinationPath '%PKG%.zip' -Force"
if errorlevel 1 (
  echo 压缩失败，请确认 PowerShell 可用。
  exit /b 1
)

echo [4/4] 完成。
echo 交付包：%PKG%.zip
dir /b "%DIST%"
endlocal
