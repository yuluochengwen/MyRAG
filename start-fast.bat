@echo off
chcp 65001 >nul
title RAG Knowledge Base System - Fast Start

echo ========================================
echo   RAG Knowledge Base System
echo   Fast Start Mode (Skip checks)
echo ========================================
echo.

REM Activate conda environment
echo [1/2] Activating Conda environment MyRAG...
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot activate Conda environment MyRAG
    pause
    exit /b 1
)
echo [OK] Environment activated
echo.

REM Start service directly
echo [2/2] Starting FastAPI service...
cd Backend
echo.
echo ========================================
echo   Service Starting...
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

uvicorn main:app --reload --host 0.0.0.0 --port 8000

cd ..
echo.
echo [INFO] Service stopped
pause
