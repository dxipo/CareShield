# 颐安盾——多模态居家老人智能风险防控平台

英文名：**Elderly AI Safety Platform**

本项目面向“揭榜挂帅——基于多模态 AI 监测的老年人跌倒风险、心理健康、诈骗识别及预警研究”，计划支持跌倒风险评估、实时跌倒检测和诈骗风险识别。目标摄像设备为 EZVIZ CS-H6c (8WFL, 4mm)。

## 当前阶段：M4 AI Realtime Pipeline

M0–M3.1 已完成基础工程、Dashboard、真实萤石设备和 H.265 实时音视频链路。M4 新增独立 CPU-only AI Worker、统一 `AlgorithmResult`、内部鉴权、Redis 实时状态、单一 WebSocket 和 Vue realtime client。M4 只验证基础设施，未安装或运行任何真实 AI 模型，也不包含 CUDA、PyTorch 和 NVIDIA Container Toolkit。

当前能力状态：

| 能力 | 状态 |
| --- | --- |
| EZVIZ device query | Implemented in M2 |
| EZVIZ H.265 HLS live streaming | Implemented in M3.1; manual visual verification gate |
| Media diagnostics | Implemented in M3.1; probe and content verification are separate |
| AI realtime infrastructure | Implemented in M4; pipeline test is explicitly simulated |
| AI models | Not installed |
| Fall Detection | Not implemented |
| Fall Risk | Not implemented |
| Fraud Detection | Not implemented |

## 技术架构

- Frontend：Vue 3 + TypeScript + Vite + Vue Router + Element Plus + EZUIKit HLS Player
- Backend：Python + FastAPI + Uvicorn + HTTPX + Redis client + ffprobe
- Data services：PostgreSQL + Redis（M4 用于 Worker TTL 和 latest result）
- AI Worker：独立 CPU-only FastAPI 服务，统一发布结果与 heartbeat
- Deployment：Docker Compose
- Reverse proxy：Nginx 目录已预留，M0 不加入访问链路

浏览器请求相对地址 `/api/*`。开发环境和 Compose 环境均由 Vite 将请求代理到 FastAPI，因此前端不接触 AppSecret 或 AccessToken，也不依赖写死的后端主机地址。

M4 实时结果链：

```text
AI Worker -> ResultPublisher -> Backend internal API -> Redis -> /ws/realtime -> Vue
```

M2/M3 设备与媒体调用链：

```text
Frontend -> CareShield API Route -> Device Service -> EZVIZ Adapter -> EZVIZ Open API
Frontend -> CareShield Stream API -> Stream Service -> EZVIZ Stream Adapter -> temporary HLS
Backend ffprobe -----------------------------> temporary HLS -> safe media metadata
```

## 目录结构

```text
.
├── frontend/          # Vue 前端
├── backend/           # FastAPI 后端
├── ai-worker/         # 独立 CPU-only Worker 服务
├── shared/            # Backend / Worker 共享数据契约
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

M4 不要求 GPU。未来的 RTX 4090、CUDA 和 PyTorch 支持将在真实模型阶段单独引入。

## 本地启动

后端：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=shared/python uvicorn app.main:app --app-dir backend --reload --port 8000
```

另开终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。后端健康检查可直接访问 <http://localhost:8000/api/health>。

本地运行 AI Worker 时同样加载共享契约（需先启动 Redis 与 Backend，并配置内部 token）：

```bash
PYTHONPATH=shared/python uvicorn app.main:app --app-dir ai-worker --reload --port 8080
```

### 配置 EZVIZ

仅在本机仓库根目录的 `.env` 中配置真实凭据：

```env
EZVIZ_APP_KEY=your_app_key
EZVIZ_APP_SECRET=your_app_secret
EZVIZ_API_BASE_URL=https://open.ys7.com
```

真实 AppKey、AppSecret 和 AccessToken 不得写入前端、文档或 Git。未配置时 Backend 仍可启动，`GET /api/health` 保持正常，EZVIZ 状态显示为未配置。修改配置后需重启 Backend。

M2 API：

- `GET /api/integrations/ezviz/status`：仅返回是否已配置、是否可达及安全错误摘要。
- `GET /api/devices`：返回 CareShield 标准化设备列表。
- `GET /api/devices/{device_serial}`：返回标准化单设备信息。

M3 API：

- `GET /api/devices/{device_serial}/stream`：运行时获取一小时有效的 HLS 预览地址。
- `GET /api/devices/{device_serial}/media-info`：实时探测并仅返回安全的音视频元数据。

M4 API：

- `GET /api/algorithms`：Worker、Redis、capabilities 和最近 pipeline test 状态。
- `GET /api/algorithms/workers`：当前 TTL 内的在线 Worker。
- `GET /api/system/status`：Backend、Redis 和 AI Worker 安全状态摘要。
- `POST /internal/ai/results`、`POST /internal/ai/heartbeat`：需要内部 Bearer token，不供浏览器调用。
- `/ws/realtime`：浏览器唯一实时通道。

播放地址属于临时敏感资源，仅由 Backend 运行时获取并交给播放器，不写入 `.env`、数据库、日志、测试 fixture 或文档。媒体诊断 API 不返回播放地址。

API 不向浏览器返回 AppSecret 或 AccessToken。普通设备页面会对设备序列号脱敏显示。

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

AI Worker 与 Frontend realtime 测试：

```bash
python -m pytest ai-worker/tests
cd frontend
npm test
```

前端类型检查与生产构建：

```bash
cd frontend
npm run build
```

本机通过 CareShield API 获取临时地址并执行真实 ffprobe（只输出媒体元数据）：

```bash
python3 scripts/probe_ezviz_stream.py
```

## M0 已完成内容

- Vue 3 + TypeScript + Vite 简单状态页
- FastAPI `GET /api/health`
- 前端通过 `/api` 代理读取后端健康状态
- 后端基础 pytest
- Frontend、Backend、PostgreSQL、Redis Compose 服务
- PostgreSQL 与 Redis 容器 health check
- AI Worker、共享契约、Nginx、数据与模型目录占位说明

## M1 当前已完成内容

- 统一的桌面 Dashboard 布局、侧边导航和顶部栏
- 综合首页、实时监测、跌倒风险、跌倒检测、诈骗风险、风险事件、设备管理、算法管理和系统状态路由
- 无真实业务数据区域统一显示“未接入”或 Empty State
- Dashboard 与系统状态页继续读取真实 `GET /api/health`
- 摄像头、风险趋势与事件区域仅提供明确占位，不使用测试视频或模拟 AI 数据

## M2 当前已完成内容

- EZVIZ AppKey/AppSecret 仅从 Backend 环境变量读取
- AccessToken 进程内缓存、按官方 `expireTime` 临期刷新，并处理 `10002` 失效返回
- 真实萤石设备分页查询和单设备详情查询
- CareShield 标准化 Device Schema，不透传萤石原始响应
- `/devices` 的 Loading、未配置、无设备、失败和真实设备列表状态
- Dashboard 在线设备卡片读取真实 `/api/devices` 结果
- EZVIZ HTTP 调用使用 Mock Transport 的 Backend 单元测试，不依赖真实网络

更多 Adapter 说明和安全调试方法见 [docs/ezviz-integration.md](docs/ezviz-integration.md)。

## M3 当前已完成内容

- 通过官方 `POST /api/lapp/v2/live/address/get` 显式请求 H.265、TS、非静音的标准 HLS 实时预览地址
- Stream Route、Service、EZVIZ Stream Adapter 分层，API 不直接访问第三方 HTTP
- `/monitor` 使用官方 `@ezuikit/player-hls` WASM 软解；只有人工确认画面内容后才显示 `LIVE`
- Backend 镜像内安装 ffprobe，`media-info` 返回安全媒体元数据，并明确 `probe_success` 不等于真实摄像画面已验证
- 本机诊断脚本不硬编码、不打印、不保存设备序列号、Token、Secret 或播放地址
- Stream 和媒体映射使用 Mock/Fake 的单元测试，不依赖真实 H6c 或网络

更多协议选择、安全边界与调试方式见 [docs/ezviz-streaming.md](docs/ezviz-streaming.md)。

## M4 当前已完成内容

- Backend 与 AI Worker 共用唯一 `AlgorithmResult` 契约，score、task、level 和模拟标记均强校验
- 独立 AI Worker health、真实 capabilities、heartbeat 与统一 `ResultPublisher`
- 内部 Bearer 鉴权，Worker 短 TTL 和 Redis latest result TTL
- 单一 `/ws/realtime` envelope 与 Vue 集中式自动重连客户端
- `/algorithms` 显示真实 Worker、Redis、WebSocket 和未安装模型状态
- `/system` 显示真实 AI 基础设施状态
- 开发用 pipeline test 明确 `simulated=true`，不进入 Dashboard 或风险业务页面

架构、契约与安全策略见 [docs/ai-realtime-pipeline.md](docs/ai-realtime-pipeline.md)。

## 尚未实现

RTMP/HTTP-FLV、PTZ、截图、云录像、历史回放、双向语音、设备事件、PyAV、ASR、姿态估计、AI 模型、跌倒检测、跌倒风险评估、诈骗识别、用户系统、业务数据库表、告警业务和 Nginx 访问链路均未实现。M4 的 pipeline test 只是明确标记的传输诊断，不是 AI 输出。
