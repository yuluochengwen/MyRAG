@echo off
chcp 65001 >nul
title RAG Knowledge Base System - Fast Start

echo ========================================
echo   RAG Knowledge Base System
echo   Fast Start Mode (Skip checks)
echo ========================================
echo.

REM Activate conda environment
echo [1/3] Activating Conda environment MyRAG...
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot activate Conda environment MyRAG
    pause
    exit /b 1
)
echo [OK] Environment activated
echo.

REM Check and create .env if missing
echo [2/3] Checking configuration...
if not exist "Backend\.env" (
    echo [INFO] Backend\.env not found. Creating default configuration...
    (
        echo MYSQL_HOST=localhost
        echo MYSQL_PORT=3306
        echo MYSQL_USER=root
        echo MYSQL_PASSWORD=123456
        echo MYSQL_DATABASE=myrag
    ) > "Backend\.env"
    echo [OK] Created Backend\.env with default settings
) else (
    echo [OK] Configuration found
)
echo.

REM Start service directly
echo [3/3] Starting FastAPI service...
echo.
echo ========================================
echo   Service Starting...
echo   Please ensure MySQL is running on localhost:3306
echo ========================================
echo.
echo Access URLs:
echo   Frontend: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Health Check: http://localhost:8000/health
echo.
echo Press Ctrl+C to stop
echo ========================================
echo.

uvicorn main:app --app-dir Backend --reload --host 0.0.0.0 --port 8000

echo.
echo [INFO] Service stopped
pause
