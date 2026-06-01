# ============================================================
# Hermes Dashboard — Backend Dockerfile (Python + Uvicorn)
# ============================================================
# 构建:
#   docker build -t hermes-dashboard-backend .
#   docker compose build backend
# ============================================================

FROM python:3.12-slim

LABEL maintainer="Hermes Dashboard Team"
LABEL description="Hermes Dashboard Backend — FastAPI + Uvicorn"
LABEL version="0.1.0"

# ── 环境变量 ──────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    TZ=Asia/Shanghai

# ── 安装系统依赖（仅最小必要集合）──────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 复制后端代码 ─────────────────────────────────────────
COPY backend/ ./backend/

# ── 安装 Python 依赖 ────────────────────────────────────
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# ── 健康检查 ────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8090/health || exit 1

# ── 使用 tini 作为 init 进程 ────────────────────────────
ENTRYPOINT ["/usr/bin/tini", "--"]

# ── 启动命令 ────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "2", "--log-level", "info"]

EXPOSE 8090
