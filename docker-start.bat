@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo MyRAG Docker Deployment Script
echo ========================================
echo.

:: Check if Docker is running
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running, please start Docker Desktop first
    pause
    exit /b 1
)

echo [INFO] Docker is ready
echo.

:: Show menu
:menu
echo Please select an option:
echo 1. Start all services
echo 2. Stop all services
echo 3. View service status
echo 4. View logs
echo 5. Download Ollama models
echo 6. Preload models (Ollama + HuggingFace)
echo 7. Rebuild and start
echo 8. Clean all (including data)
echo 9. Exit
echo.
set /p choice=Enter option (1-9): 

if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto status
if "%choice%"=="4" goto logs
if "%choice%"=="5" goto ollama
if "%choice%"=="6" goto preload_all
if "%choice%"=="7" goto rebuild
if "%choice%"=="8" goto clean
if "%choice%"=="9" goto end
echo [ERROR] Invalid option, please try again
goto menu

:start
echo.
echo [RUN] Starting all services
docker-compose up -d
if %errorlevel% equ 0 (
    echo [SUCCESS] Services started
    echo.
    echo Access URLs:
    echo - Frontend: http://localhost
    echo - API Docs: http://localhost:8000/docs
    echo.
    timeout /t 3 >nul
) else (
    echo [ERROR] Failed to start
    pause
)
goto menu

:stop
echo.
echo [RUN] Stopping all services
docker-compose down
if %errorlevel% equ 0 (
    echo [SUCCESS] Services stopped
) else (
    echo [ERROR] Failed to stop
)
timeout /t 2 >nul
goto menu

:status
echo.
echo [INFO] Service status:
docker-compose ps
echo.
pause
goto menu

:logs
echo.
echo Select logs to view:
echo 1. All services
echo 2. Backend service
echo 3. MySQL service
echo 4. Ollama service
echo 5. Nginx service
echo 6. Return to main menu
echo.
set /p logchoice=Enter option (1-6): 

if "%logchoice%"=="1" docker-compose logs --tail=100 -f
if "%logchoice%"=="2" docker-compose logs backend --tail=100 -f
if "%logchoice%"=="3" docker-compose logs mysql --tail=100 -f
if "%logchoice%"=="4" docker-compose logs ollama --tail=100 -f
if "%logchoice%"=="5" docker-compose logs nginx --tail=100 -f
if "%logchoice%"=="6" goto menu
goto menu

:ollama
echo.
echo [INFO] Ollama Model Download
echo.
echo Select model to download:
echo 1. qwen2.5:7b (Recommended, 7B params)
echo 2. deepseek-r1:1.5b (Lightweight, 1.5B params)
echo 3. deepseek-r1:8b (Medium, 8B params)
echo 4. nomic-embed-text (Embedding model)
echo 5. Download all
echo 6. Custom model
echo 7. Return to main menu
echo.
set /p modelchoice=Enter option (1-7): 

if "%modelchoice%"=="1" (
    echo [RUN] Downloading qwen2.5:7b
    docker exec myrag-ollama ollama pull qwen2.5:7b
)
if "%modelchoice%"=="2" (
    echo [RUN] Downloading deepseek-r1:1.5b
    docker exec myrag-ollama ollama pull deepseek-r1:1.5b
)
if "%modelchoice%"=="3" (
    echo [RUN] Downloading deepseek-r1:8b
    docker exec myrag-ollama ollama pull deepseek-r1:8b
)
if "%modelchoice%"=="4" (
    echo [RUN] Downloading nomic-embed-text
    docker exec myrag-ollama ollama pull nomic-embed-text
)
if "%modelchoice%"=="5" (
    echo [RUN] Downloading all models
    docker exec myrag-ollama ollama pull qwen2.5:7b
    docker exec myrag-ollama ollama pull deepseek-r1:1.5b
    docker exec myrag-ollama ollama pull deepseek-r1:8b
    docker exec myrag-ollama ollama pull nomic-embed-text
)
if "%modelchoice%"=="6" (
    set /p custommodel=Enter model name (e.g. llama3:8b): 
    echo [RUN] Downloading !custommodel!
    docker exec myrag-ollama ollama pull !custommodel!
)
if "%modelchoice%"=="7" goto menu

echo.
echo [RUN] Listing installed models
docker exec myrag-ollama ollama list
echo.
pause
goto menu

:preload_all
echo.
echo ========================================
echo Preload All Models (Ollama + HuggingFace)
echo ========================================
echo.
echo This will download:
echo   - Ollama: qwen2.5:1.5b (~1GB)
echo   - Ollama: nomic-embed-text (~274MB)
echo   - HuggingFace: paraphrase-multilingual-MiniLM-L12-v2 (~471MB)
echo.
echo Total download size: ~1.7GB
echo This may take 10-30 minutes depending on your network speed.
echo.
set /p confirm=Continue? (Y/N): 
if /i not "%confirm%"=="Y" goto menu

echo.
echo [STEP 1/2] Downloading Ollama models...
echo ========================================
docker exec myrag-ollama ollama pull qwen2.5:1.5b
if %errorlevel% equ 0 (
    echo [SUCCESS] qwen2.5:1.5b downloaded
) else (
    echo [WARNING] Failed to download qwen2.5:1.5b
)

docker exec myrag-ollama ollama pull nomic-embed-text
if %errorlevel% equ 0 (
    echo [SUCCESS] nomic-embed-text downloaded
) else (
    echo [WARNING] Failed to download nomic-embed-text
)

echo.
echo [STEP 2/2] Downloading HuggingFace models...
echo ========================================
docker exec myrag-backend python /app/../scripts/preload-huggingface-models.py
if %errorlevel% equ 0 (
    echo [SUCCESS] HuggingFace models downloaded
) else (
    echo [WARNING] Failed to download HuggingFace models
)

echo.
echo ========================================
echo Model Preloading Completed!
echo ========================================
echo.
echo Installed Ollama models:
docker exec myrag-ollama ollama list
echo.
echo You can now use these models in your config.yaml:
echo   - LLM: qwen2.5:1.5b
echo   - Embedding (Ollama): nomic-embed-text
echo   - Embedding (HuggingFace): paraphrase-multilingual-MiniLM-L12-v2
echo.
pause
goto menu

:rebuild
echo.
echo [WARNING] This will stop all services and rebuild
set /p confirm=Confirm? (Y/N): 
if /i not "%confirm%"=="Y" goto menu

echo [RUN] Stopping services
docker-compose down
echo [RUN] Rebuilding and starting
docker-compose up -d --build
if %errorlevel% equ 0 (
    echo [SUCCESS] Services rebuilt and started
) else (
    echo [ERROR] Rebuild failed
)
pause
goto menu

:clean
echo.
echo [WARNING] This will delete all containers, networks and volumes
echo [WARNING] All data will be permanently deleted!
set /p confirm=Confirm? (Y/N): 
if /i not "%confirm%"=="Y" goto menu

echo [RUN] Cleaning all
docker-compose down -v
if %errorlevel% equ 0 (
    echo [SUCCESS] Cleaned successfully
) else (
    echo [ERROR] Clean failed
)
pause
goto menu

:end
echo.
echo Thank you for using!
timeout /t 1 >nul
exit /b 0
