@echo off
title Project Setup

echo ===============================================
echo      Project Environment Setup Script
echo ===============================================
echo.

:: 1. 检查Python环境
echo [1/4] Checking for Python installation...
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not found in your system's PATH.
    echo Please install Python (and add it to PATH) before running this script.
    pause
    exit /b 1
)
echo Python installation found.
echo.

:: 2. 检查 requirements.txt 文件
echo [2/4] Checking for requirements.txt file...
if not exist requirements.txt (
    echo ERROR: requirements.txt not found.
    echo Please make sure this script is in the same folder as requirements.txt.
    pause
    exit /b 1
)
echo requirements.txt found.
echo.

:: 3. 创建虚拟环境 (如果 venv 文件夹不存在)
echo [3/4] Setting up virtual environment...
if not exist venv (
    echo      Creating virtual environment 'venv'...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create the virtual environment.
        pause
        exit /b 1
    )
    echo      Virtual environment created successfully.
) else (
    echo      Virtual environment 'venv' already exists. Skipping creation.
)
echo.

:: 4. 激活虚拟环境并安装依赖
echo [4/4] Installing dependencies from requirements.txt...
call venv\Scripts\activate.bat
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies. Please check your internet connection and requirements.txt.
    pause
    exit /b 1
)
echo Dependencies installed successfully.
echo.

echo ===============================================
echo      Setup Complete!
echo You can now run the application using run.bat
echo ===============================================
echo.
pause 