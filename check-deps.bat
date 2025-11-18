@echo off
chcp 65001 >nul
title Check Dependencies

echo ========================================
echo   Checking and Installing Dependencies
echo ========================================
echo.

REM Activate conda environment
echo [1/3] Activating Conda environment MyRAG...
call E:\Anaconda\Scripts\activate.bat MyRAG 2>nul
if errorlevel 1 (
    echo [ERROR] Cannot activate Conda environment MyRAG
    echo Please create it first: conda create -n MyRAG python=3.11
    pause
    exit /b 1
)
echo [OK] Environment activated
echo.

REM Check core dependencies
echo [2/3] Checking core dependencies...
cd Backend

set MISSING=0

python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [MISSING] fastapi
    set MISSING=1
)

python -c "import uvicorn" 2>nul
if errorlevel 1 (
    echo [MISSING] uvicorn
    set MISSING=1
)

python -c "import torch" 2>nul
if errorlevel 1 (
    echo [MISSING] torch
    set MISSING=1
)

python -c "import sentence_transformers" 2>nul
if errorlevel 1 (
    echo [MISSING] sentence-transformers
    set MISSING=1
)

if %MISSING%==1 (
    echo.
    echo [3/3] Installing missing dependencies...
    echo This may take several minutes...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        cd ..
        pause
        exit /b 1
    )
    echo [OK] All dependencies installed
) else (
    echo [OK] All dependencies are ready
    echo [3/3] No installation needed
)

cd ..
echo.
echo ========================================
echo   Dependency Check Complete
echo ========================================
echo.
pause
