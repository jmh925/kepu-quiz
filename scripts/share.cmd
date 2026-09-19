@echo off
REM ============================================================
REM  科普知识闯关系统 · 一键对外演示（Windows）
REM  用法：双击本文件，或在命令行执行 scripts\share.cmd
REM
REM  它会做四件事：
REM    1. 启动服务端（已经在跑就直接复用，不重复起）
REM    2. 建立 Cloudflare 免费临时隧道（cloudflared 会自动下载到用户目录）
REM    3. 等到公网地址真的返回 200，才把地址打印出来
REM    4. 打印学生端 / 管理端地址与管理员口令
REM
REM  结束后按 Ctrl+C：隧道会关掉；服务端只在"是本脚本起的"时候才关。
REM ============================================================
setlocal
set "ROOT=%~dp0.."

if "%KEPU_PYTHON%"=="" set "KEPU_PYTHON=python"
if exist "%ROOT%\backend\deps" set "PYTHONPATH=%ROOT%\backend\deps"

cd /d "%ROOT%"
title kepu-quiz 对外演示（Ctrl+C 结束）
"%KEPU_PYTHON%" -X utf8 tools\share.py %*

echo.
echo [kepu] 已结束。按任意键关闭这个窗口。
pause >nul
endlocal
