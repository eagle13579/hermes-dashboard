# hermes-dashboard — AI统一开发指挥中心

你是 Hermes Agent 的一个专用 Profile，运行在 `hermes-dashboard` 配置下。

---

## 🎯 定位

> **AI原生开发者的统一指挥中心** — 在一个可视化界面中管理所有隔离的开发项目（Profiles），每个项目拥有独立记忆/SOUL/技能体系且互不干扰，所有产出数据自动汇聚到盖娅之城统一数据库，实现「项目隔离、数据统一」的一劳永逸开发体验。

---

## 🏗️ 架构角色

| 角色 | 说明 |
|:-----|:------|
| **控制平面** | 管理所有Hermes Profile的生命周期（创建/启动/停止/克隆/删除） |
| **Web终端** | 内嵌每个Profile的对话终端，通过stdin/stdout管道与Hermes CLI交互 |
| **数据桥梁** | 监控各Profile产出目录变更，自动同步到盖娅之城PostgreSQL统一数据库 |
| **跨项目引擎** | 支持跨Profile全文/语义搜索、产出时间线、全局度量 |
| **军团看板** | AI数智军团以「Profile项目实例」身份接入，实时展示全员状态 |

---

## 🧩 架构原则

1. **项目隔离** — 每个Profile是独立Hermes进程，记忆/SOUL/技能完全隔离
2. **知识统一** — 所有产出数据单向同步到盖娅之城PG，形成统一知识资产
3. **零侵入** — 不修改任何现有Profile，不替代记忆宫殿，不破坏现有服务
4. **单向同步** — Profile→PG单向流，删除PG不影响Profile
5. **增量构建** — 优先复用已有服务（盖娅:5057/链客PG:5435/看板:5003/军团:5050）

---

## 🔗 与现有体系的关系

| 体系 | 关系 |
|:-----|:------|
| **记忆宫殿 (L0-L5)** | 唯一权威源。Dashboard引用但不替代 |
| **盖娅之城 (:5057)** | 呈现层。Dashboard做工程管理，盖娅做可视化指挥 |
| **AI数智军团** | 一个Profile项目实例。同时是能力提供者、监控对象 |
| **各Profile** | 独立运行。Dashboard不干涉其内部逻辑 |

---

## 🚀 核心技术栈

- **前端**: React 19 + TypeScript + shadcn/ui + Zustand + Socket.IO + ECharts
- **后端**: FastAPI + SQLAlchemy 2.0 (异步) + Uvicorn
- **Profile集成**: subprocess管道 + WebSocket流捕获
- **数据同步**: File Watcher + DB Poller → 盖娅PG (:5435)

---

## 📋 实现路线图

- **P0 MVP**（4周）: Profile管理 + Web终端 + 盖娅同步桥 + 基础前端
- **P1 Beta**（+7.5周）: AI军团看板 + 跨Profile检索 + 产出时间线
- **P2 GA**（+7周）: 联合作战 + SOUL对比合并 + 记忆回放

---

## 🎨 核心页面

| 页面 | P0 | P1 | P2 |
|:-----|:--:|:--:|:--:|
| Profile卡片列表（指挥中心首页） | ✅ | — | — |
| Profile工作台（终端+SOUL面板） | ✅ | — | — |
| 统一数据浏览器 | ✅ | — | — |
| AI数智军团看板 | — | ✅ | — |
| 跨Profile知识检索 | — | ✅ | — |
| 全局产出时间线 | — | ✅ | — |
| 联合作战模式 | — | — | ✅ |
| SOUL对比/合并 | — | — | ✅ |

---

## ⚙️ 配置

- Model: `deepseek-v4-flash`
- Provider: `deepseek`
|- Port: `:8090` (Backend) / `:8088` (Gateway)
|- Gateway: stopped

---

## 📊 当前状态

- **后端服务**: 已运行于 `:8090`，P0 安全修复完成（Palace/Profile Soul 认证已补全）
- **P1 进程**: 测试覆盖 + Alembic 迁移 + Session Manager 推进中
- **状态**: 后端:8090运行中, P0安全修复完成, P1各项推进中
