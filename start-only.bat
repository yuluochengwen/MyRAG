@echo off
chcp 65001 >nul
title MyRAG - Start Only

echo ========================================
echo   MyRAG - Start Only
echo   Conda Environment: MyRAG
echo ========================================
echo.

REM Step 1: Activate Conda
echo [1/2] Activating Conda environment MyRAG...
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot activate Conda environment MyRAG
    echo Please create it first: conda create -n MyRAG python=3.11
    pause
    exit /b 1
)
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not available after activation
    pause
    exit /b 1
)
echo [OK] Environment activated
echo.

REM Step 2: Start service only (no dependency check, no DB init)
echo [2/2] Starting FastAPI service...
echo.
echo ========================================
echo   Service Starting
echo ========================================
echo.
echo   Frontend:     http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo   Health Check: http://localhost:8000/health
echo.
echo   Press Ctrl+C to stop
echo ========================================
echo.

REM Ensure data directories exist
if not exist "data\knowledge_base" mkdir "data\knowledge_base"
if not exist "data\vector_db" mkdir "data\vector_db"
if not exist "data\logs" mkdir "data\logs"
if not exist "data\training_data" mkdir "data\training_data"

REM Ensure Backend package path is importable (for `from app...` imports)
set "PYTHONPATH=%CD%\Backend;%PYTHONPATH%"

python -m uvicorn Backend.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo [INFO] Service stopped
pause
