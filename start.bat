@echo off
chcp 65001 >nul
title MyRAG - RAG Knowledge Base System

echo ========================================
echo   MyRAG - RAG Knowledge Base System
echo   Conda Environment: MyRAG
echo ========================================
echo.
echo Usage: start.bat [fast]
echo   fast  - Skip dependency check and DB init
echo.

REM Parse arguments
set "FAST_MODE=0"
if /i "%~1"=="fast" set "FAST_MODE=1"

REM ---- Step 1: Activate Conda ----
echo [1/4] Activating Conda environment MyRAG...
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

REM ---- Step 2: Check .env ----
echo [2/4] Checking configuration...
if not exist "Backend\.env" (
    echo [INFO] Creating Backend\.env with defaults...
    (
        echo MYSQL_HOST=localhost
        echo MYSQL_PORT=3306
        echo MYSQL_USER=root
        echo MYSQL_PASSWORD=123456
        echo MYSQL_DATABASE=myrag
    ) > "Backend\.env"
    echo [OK] Created Backend\.env
) else (
    echo [OK] Configuration found
)
echo.

REM ---- Step 3: Dependencies + DB (skip in fast mode) ----
if "%FAST_MODE%"=="1" (
    echo [3/4] Skipped (fast mode^)
    echo.
    goto :start_service
)

echo [3/4] Checking dependencies ^& database...
if exist "Backend\.deps_ready" (
    echo [OK] Dependencies ready (cached^)
    goto :init_db
)
python -c "import fastapi, uvicorn, torch" 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies (first run^)...
    pip install -r Backend\requirements.txt --quiet --no-warn-script-location
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready
type nul > Backend\.deps_ready

:init_db
python Backend\scripts\init_db.py 2>nul
if errorlevel 1 (
    echo [WARNING] Database init skipped (may already be initialized^)
) else (
    echo [OK] Database initialized
)
echo.

REM ---- Step 4: Start service ----
:start_service
echo [4/4] Starting FastAPI service...
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
