# 颐安盾——多模态居家老人智能风险防控平台

英文名：**Elderly AI Safety Platform**

本项目面向“揭榜挂帅——基于多模态 AI 监测的老年人跌倒风险、心理健康、诈骗识别及预警研究”，计划支持跌倒风险评估、实时跌倒检测和诈骗风险识别。目标摄像设备为 EZVIZ CS-H6c (8WFL, 4mm)。

## 当前阶段：M0

M0 只验证基础工程、前后端 HTTP 通信及 PostgreSQL/Redis 容器健康状态，不包含摄像头、视频或 AI 业务实现，也不包含 CUDA、PyTorch 和 NVIDIA Container Toolkit 依赖。

当前能力状态：

| 能力 | 状态 |
| --- | --- |
| EZVIZ | Not implemented |
| Video streaming | Not implemented |
| AI | Not implemented |
| Fall Detection | Not implemented |
| Fall Risk | Not implemented |
| Fraud Detection | Not implemented |

## 技术架构

- Frontend：Vue 3 + TypeScript + Vite
- Backend：Python + FastAPI + Uvicorn
- Data services：PostgreSQL + Redis（M0 尚未接入业务）
- AI Worker：独立模块，M0 仅预留目录
- Deployment：Docker Compose
- Reverse proxy：Nginx 目录已预留，M0 不加入访问链路

浏览器请求相对地址 `/api/health`。开发环境和 Compose 环境均由 Vite 将该请求代理到 FastAPI，因此前端不依赖写死的后端主机地址。

## 目录结构

```text
.
├── frontend/          # Vue 前端
├── backend/           # FastAPI 后端
├── ai-worker/         # 独立 AI Worker 预留目录
├── shared/            # 跨模块契约说明
├── infra/nginx/       # Nginx 配置预留
├── data/              # 本地数据（内容不入库）
├── models/            # 模型权重（内容不入库）
├── docs/              # 文档
├── scripts/           # 开发/运维脚本
├── docker-compose.yml
└── .env.example
```

## 环境要求

- Ubuntu 22.04（目标部署环境）
- Node.js 20.19+ 或 22.12+
- Python 3.11+
- Docker Engine 与 Docker Compose v2（Docker 启动方式需要）

M0 不要求 GPU。未来的 RTX 4090、CUDA 和 PyTorch 支持将在 AI Worker 阶段单独引入。

## 本地启动

后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --reload --port 8000
```

另开终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。页面应显示 `Frontend Status: OK`，并显示后端返回的 `status` 与 `service`。后端健康检查也可直接访问 <http://localhost:8000/api/health>。

## Docker 启动

首次启动前创建本地环境文件，并将示例密码换成本地专用密码：

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

访问 <http://localhost:5173>。停止服务：

```bash
docker compose down
```

`.env` 已被 Git 忽略。请勿将真实密码、Token、AppKey 或 AppSecret 写入代码或提交到仓库。

## 测试

后端测试：

```bash
python -m pytest backend/tests
```

前端类型检查与生产构建：

```bash
cd frontend
npm run build
```

## M0 已完成内容

- Vue 3 + TypeScript + Vite 简单状态页
- FastAPI `GET /api/health`
- 前端通过 `/api` 代理读取后端健康状态
- 后端基础 pytest
- Frontend、Backend、PostgreSQL、Redis Compose 服务
- PostgreSQL 与 Redis 容器 health check
- AI Worker、共享契约、Nginx、数据与模型目录占位说明

## 尚未实现

萤石开放平台和设备 Adapter、视频流、音频、设备事件、FFmpeg/PyAV、ASR、姿态估计、AI 模型、跌倒检测、跌倒风险评估、诈骗识别、用户系统、业务数据库表、告警业务和 Nginx 访问链路均未实现。
