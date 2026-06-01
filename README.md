# hermes-dashboard — AI统一开发指挥中心

> 北极星成熟度: 7.5/10 · 工业化开发平台

## 一键启动

```bash
docker compose up -d
# 访问: http://localhost:3000
```

## 技术栈

- **后端**: FastAPI + SQLite + SSE
- **前端**: React 19 + TypeScript + Vite + Tailwind + ECharts
- **部署**: Docker Compose (backend:8090, frontend:3000)

## 核心功能

| 功能 | 说明 |
|:-----|:------|
| Profile管理 | 创建/启动/停止/克隆Hermes Profile |
| Kanban看板 | 4列状态流转 + 拖拽 + 自动规则引擎 |
| 健康驾驶舱 | ECharts趋势图 + 服务列表 + 在线率 |
| SSE日志流 | EventSource实时日志 |
| 测试覆盖 | 160测试 / 90%覆盖率 |
| 文档完整 | ADR决策记录 / 心智模型 / 复盘 |
