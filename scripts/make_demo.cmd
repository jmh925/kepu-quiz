@echo off
REM ============================================================
REM  生成并打开「浏览器可交互演示页」（Windows）
REM  用途：没有微信开发者工具时，也能先在浏览器里把小程序流程点一遍
REM  前置：后端需在运行（另开一个窗口跑 scripts\run_server.cmd）
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "PY=%KEPU_PYTHON%"
if "%PY%"=="" set "PY=python"

cd /d "%ROOT%"
echo [1/3] 生成演示页 ...
node tools\make_demo.js || goto :fail

echo [2/3] 自检并截图 ...
"%PY%" tools\verify_demo.py

echo [3/3] 打开演示页 ...
start "" "%ROOT%\demo\index.html"
echo.
echo 演示页：%ROOT%\demo\index.html
echo 截图目录：%ROOT%\demo\shots
goto :eof

:fail
echo 生成失败：请确认已安装 Node.js（node --version 可验证）。
exit /b 1
endlocal
