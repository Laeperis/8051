@echo off
title Application Launcher

:: 设置项目主程序的文件名
set MAIN_SCRIPT=upper_com_qt.py

:: 检查虚拟环境是否存在
if not exist venv\Scripts\activate.bat (
    echo ERROR: Virtual environment not found.
    echo Please run setup.bat first to set up the environment.
    pause
    exit /b 1
)

:: 激活虚拟环境并启动主应用程序
echo Activating environment and launching the application...
echo.
call venv\Scripts\activate.bat
python %MAIN_SCRIPT%

echo.
echo Application has been closed.
pause 