# ============================================================
# Hermes Dashboard — Frontend Dockerfile (Vite + Nginx)
# ============================================================
# 构建:
#   docker build -t hermes-dashboard-frontend .
#   docker compose build frontend
# ============================================================

# ============================================================
# Stage 1: 前端构建 (Node.js + Vite + React + TypeScript)
# ============================================================
FROM node:20-alpine AS builder

WORKDIR /app

# 单独复制 package.json 以利用 Docker 缓存层
COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

# 复制前端源码并构建
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public/ ./public/
COPY src/ ./src/

RUN npm run build

# ============================================================
# Stage 2: Nginx 静态文件服务
# ============================================================
FROM nginx:1.27-alpine

LABEL maintainer="Hermes Dashboard Team"
LABEL description="Hermes Dashboard Frontend — Nginx Static Files + API Reverse Proxy"
LABEL version="0.1.0"

ENV TZ=Asia/Shanghai

# 从 builder 阶段复制构建产物
COPY --from=builder /app/dist/ /usr/share/nginx/html/

# 复制 Docker 专用 Nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:80/ || exit 1

EXPOSE 80
