@echo off
chcp 65001 >nul
title RAG Knowledge Base System

echo ========================================
echo   RAG Knowledge Base System
echo   Using Conda Environment: MyRAG
echo ========================================
echo.

REM Activate conda environment
echo [1/4] Activating Conda environment MyRAG
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot activate Conda environment MyRAG
    echo Please create it first: conda create -n MyRAG python=3.11
    pause
    exit /b 1
)

REM Verify Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not available after activation
    pause
    exit /b 1
)
echo [OK] Environment activated
echo.

REM Check and install dependencies
echo [2/4] Checking Python dependencies
cd Backend

REM Check if deps are ready
if exist ".deps_ready" (
    echo [OK] Dependencies ready (cached^)
    goto :deps_done
)

REM Quick check for key packages
python -c "import fastapi, uvicorn, torch" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies (first run^)
    pip install -r requirements.txt --quiet --no-warn-script-location
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        cd ..
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
    type nul > .deps_ready
    goto :deps_done
)

echo [OK] Dependencies ready
type nul > .deps_ready

:deps_done
echo.

REM Initialize database
echo [3/4] Initializing database
python scripts\init_db.py 2>nul
if errorlevel 1 (
    echo [WARNING] Database init skipped (may already initialized^)
) else (
    echo [OK] Database initialized
)
echo.

REM Start service
echo [4/4] Starting FastAPI service
echo.
echo ========================================
echo   Service Starting
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

python main.py

cd ..
echo.
echo [INFO] Service stopped
pause
