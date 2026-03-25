#!/bin/bash
# 预装Ollama模型脚本

echo "=========================================="
echo "MyRAG - Preloading Ollama Models"
echo "=========================================="
echo ""

# 等待Ollama服务启动
echo "[INFO] Waiting for Ollama service to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "[SUCCESS] Ollama service is ready"
        break
    fi
    attempt=$((attempt + 1))
    echo "[WAIT] Attempt $attempt/$max_attempts - waiting for Ollama..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "[ERROR] Ollama service failed to start"
    exit 1
fi

echo ""
echo "=========================================="
echo "Downloading Models (This may take a while)"
echo "=========================================="
echo ""

# 下载小型LLM模型（推荐用于快速测试）
echo "[1/2] Downloading qwen2.5:1.5b (Small LLM - ~1GB)..."
ollama pull qwen2.5:1.5b
if [ $? -eq 0 ]; then
    echo "[SUCCESS] qwen2.5:1.5b downloaded"
else
    echo "[WARNING] Failed to download qwen2.5:1.5b"
fi

echo ""

# 下载嵌入模型
echo "[2/2] Downloading nomic-embed-text (Embedding Model - ~274MB)..."
ollama pull nomic-embed-text
if [ $? -eq 0 ]; then
    echo "[SUCCESS] nomic-embed-text downloaded"
else
    echo "[WARNING] Failed to download nomic-embed-text"
fi

echo ""
echo "=========================================="
echo "Installed Models:"
echo "=========================================="
ollama list

echo ""
echo "[INFO] Model preloading completed!"
echo ""
echo "Available models:"
echo "  - qwen2.5:1.5b        : Lightweight LLM for chat (1.5B params)"
echo "  - nomic-embed-text    : Embedding model for RAG"
echo ""
echo "To download additional models, use:"
echo "  docker exec myrag-ollama ollama pull <model_name>"
echo ""
