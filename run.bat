@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
if errorlevel 1 goto badpath

if not exist ".venv\Scripts\pythonw.exe" goto noenv

start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
if errorlevel 1 goto starterr
exit /b 0

:noenv
echo.
echo   运行环境缺失：找不到 .venv\Scripts\pythonw.exe
echo   请使用安装包重新安装 Fastcut。
echo.
pause
exit /b 1

:starterr
echo.
echo   启动失败。请在当前目录打开命令行执行下面这条命令查看具体错误：
echo   .venv\Scripts\python.exe app.py
echo.
pause
exit /b 1

:badpath
echo.
echo   无法进入程序目录：%~dp0
echo   请把整个 Fastcut 文件夹放在本地硬盘后再运行。
echo.
pause
exit /b 1
