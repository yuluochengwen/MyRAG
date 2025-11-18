FROM python:3.11-slim
FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

# Write a global pip config so pip uses a fast mirror by default
RUN mkdir -p /root/.pip && \
    printf "[global]\nindex-url = %s\n" "${PIP_INDEX_URL}" > /root/.pip/pip.conf

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker layer cache
COPY requirements.txt .

# Install Python dependencies
# If you enable BuildKit (DOCKER_BUILDKIT=1) you can uncomment the following
# RUN which uses a cache mount to persist pip wheels between builds and
# speed up repeated builds:
#
# RUN --mount=type=cache,target=/root/.cache/pip \
#     pip install --upgrade pip && \
#     pip install -r requirements.txt
#
# Fallback for non-BuildKit environments: use the configured index URL
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/KnowledgeBase /app/Models /app/VectorDB /app/logs

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
