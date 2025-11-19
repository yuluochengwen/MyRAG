@echo off
chcp 65001 >nul
title 运行MyRAG测试套件

echo ========================================
echo   MyRAG 测试套件
echo ========================================
echo.

REM 激活conda环境
echo [1/2] 激活 Conda 环境 MyRAG...
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [错误] 无法激活 Conda 环境 MyRAG
    pause
    exit /b 1
)
echo [OK] 环境已激活
echo.

REM 运行测试
echo [2/2] 运行测试...
cd test
E:\Anaconda\envs\MyRAG\python.exe test_runner.py

echo.
echo ========================================
echo 测试完成
echo ========================================
pause
