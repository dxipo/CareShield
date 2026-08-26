# 颐安盾——多模态居家老人智能风险防控平台

英文名：**Elderly AI Safety Platform**

本项目面向“揭榜挂帅——基于多模态 AI 监测的老年人跌倒风险、心理健康、诈骗识别及预警研究”，计划支持跌倒风险评估、实时跌倒检测和诈骗风险识别。目标摄像设备为 EZVIZ CS-H6c (8WFL, 4mm)。

## 当前阶段：M5.1 EZOPEN Low-latency Web Playback

M0–M5 已完成基础工程、Dashboard、真实萤石音视频、统一实时结果链和 GPU 跌倒检测基线。M5.1 将浏览器预览从高延迟标准 HLS 切换为萤石官方 EZOPEN；AI Worker 继续通过 Backend 临时 HLS 地址解码同一 H6c，因为 FFmpeg/PyAV 不能直接消费私有 EZOPEN 协议。

当前能力状态：

| 能力 | 状态 |
| --- | --- |
| EZVIZ device query | Implemented in M2 |
| Browser live streaming | M5.1 EZOPEN low-latency preview |
| AI media input | H.265 HLS through authenticated Backend endpoint |
| Media diagnostics | Implemented in M3.1; probe and content verification are separate |
| AI realtime infrastructure | Implemented in M4; pipeline test is explicitly simulated |
| AI models | YOLO26n-pose installed in M5 Worker only |
| Fall Detection | M5 real pose + temporal heuristic baseline |
| Fall Risk | Not implemented |
| Fraud Detection | Not implemented |

## 技术架构

- Frontend：Vue 3 + TypeScript + Vite + Vue Router + Element Plus + EZUIKit EZOPEN Player
- Backend：Python + FastAPI + Uvicorn + HTTPX + Redis client + ffprobe
- Data services：PostgreSQL + Redis（M4 用于 Worker TTL 和 latest result）
- AI Worker：独立 FastAPI + PyTorch/CUDA + Ultralytics + PyAV 服务
- Deployment：Docker Compose
- Reverse proxy：Nginx 目录已预留，M0 不加入访问链路

浏览器请求相对地址 `/api/*`，开发与 Compose 环境均由 Vite 代理到 FastAPI。AppSecret 始终只在 Backend；萤石官方 EZOPEN Web SDK 必须在浏览器运行时接收 AccessToken，因此仅专用播放会话接口返回当前内存 Token，并设置 `no-store`。Token 不进入源码、日志、数据库或浏览器持久化存储。

M4 实时结果链：

```text
AI Worker -> ResultPublisher -> Backend internal API -> Redis -> /ws/realtime -> Vue
```

M5 真实跌倒检测链：

```text
H6c -> Backend authenticated temporary stream -> AI Worker H.265 decode
     -> frame sampling -> pose -> temporal detector -> M4 realtime result chain
```

设备与双媒体链：

```text
Frontend -> CareShield API Route -> Device Service -> EZVIZ Adapter -> EZVIZ Open API
Browser -> no-store playback session -> EZOPEN -> official EZUIKit player
AI Worker -> authenticated internal API -> temporary HLS -> PyAV/FFmpeg
Backend ffprobe ---------------------------> temporary HLS -> safe media metadata
```

## 目录结构

```text
.
├── frontend/          # Vue 前端
├── backend/           # FastAPI 后端
├── ai-worker/         # 独立 GPU/CPU Worker 与跌倒检测
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

M5 GPU 验收环境需要 RTX 4090、正常 NVIDIA Driver 和 NVIDIA Container Toolkit。核心平台仍可独立运行；无 GPU 时使用 CPU Compose override，跌倒检测应显示 unavailable，不能伪装为 Normal。

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

本地运行 AI Worker 时同样加载共享契约（需先启动 Redis 与 Backend、配置内部 token，并安装 GPU requirements）：

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cu130 -r ai-worker/requirements-gpu.txt
python -m pip install -r ai-worker/requirements-dev.txt
PYTHONPATH=shared/python uvicorn app.main:app --app-dir ai-worker --reload --port 8080
```

### 配置 EZVIZ

仅在本机仓库根目录的 `.env` 中配置真实凭据：

```env
EZVIZ_APP_KEY=your_app_key
EZVIZ_APP_SECRET=your_app_secret
EZVIZ_API_BASE_URL=https://open.ys7.com
EZVIZ_BROWSER_PLAYBACK_ENABLED=false
EZVIZ_EZOPEN_DOMAIN=open.ys7.com
```

真实 AppKey、AppSecret 和 AccessToken 不得写入前端源码、文档或 Git。可信本地部署需要在被忽略的 `.env` 中显式设置 `EZVIZ_BROWSER_PLAYBACK_ENABLED=true` 才能启用 EZOPEN Web 会话；未启用时其他 Backend 功能仍正常。修改配置后需重启 Backend。

M2 API：

- `GET /api/integrations/ezviz/status`：仅返回是否已配置、是否可达及安全错误摘要。
- `GET /api/devices`：返回 CareShield 标准化设备列表。
- `GET /api/devices/{device_serial}`：返回标准化单设备信息。

M3 API：

- `GET /api/devices/{device_serial}/stream`：运行时获取一小时有效的 HLS 预览地址。
- `GET /api/devices/{device_serial}/media-info`：实时探测并仅返回安全的音视频元数据。
- `GET /api/devices/{device_serial}/browser-playback`：M5.1 专用、禁止缓存的 EZOPEN 浏览器会话；仅官方播放器运行时使用。

M4 API：

- `GET /api/algorithms`：Worker、Redis、capabilities 和最近 pipeline test 状态。
- `GET /api/algorithms/workers`：当前 TTL 内的在线 Worker。
- `GET /api/system/status`：Backend、Redis 和 AI Worker 安全状态摘要。
- `POST /internal/ai/results`、`POST /internal/ai/heartbeat`：需要内部 Bearer token，不供浏览器调用。
- `/ws/realtime`：浏览器唯一实时通道。

M5 内部媒体 API（仅 AI Worker Bearer 鉴权）：

- `GET /internal/media/devices`：Worker 查询标准化在线设备。
- `GET /internal/media/devices/{device_serial}/stream`：运行时签发临时 HLS；不供浏览器和第三方调用。

播放地址属于临时敏感资源，仅由 Backend 运行时获取并交给播放器，不写入 `.env`、数据库、日志、测试 fixture 或文档。媒体诊断 API 不返回播放地址。

除专用 EZOPEN 浏览器播放会话外，API 不向浏览器返回 AccessToken；任何 API 都不返回 AppSecret。普通设备页面会对设备序列号脱敏显示。

## Docker 启动

首次启动前创建本地环境文件，并将示例密码换成本地专用密码：

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

无 GPU 环境使用：

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
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
- M3.1 曾使用官方 `@ezuikit/player-hls` WASM 软解与人工画面确认；该浏览器路径已在 M5.1 被 EZOPEN 替代
- Backend 镜像内安装 ffprobe，`media-info` 返回安全媒体元数据，并明确 `probe_success` 不等于真实摄像画面已验证
- 本机诊断脚本不硬编码、不打印、不保存设备序列号、Token、Secret 或播放地址
- Stream 和媒体映射使用 Mock/Fake 的单元测试，不依赖真实 H6c 或网络

更多协议选择、安全边界与调试方式见 [docs/ezviz-streaming.md](docs/ezviz-streaming.md)。

## M5.1 当前已完成内容

- `/monitor` 使用官方 `ezuikit-js` 的 EZOPEN 播放器，浏览器不再通过标准 HLS 预览。
- 首帧事件直接驱动 `LIVE` 并记录本次连接首帧耗时，移除遮挡控制区的人工确认按钮。
- EZOPEN 会话显式启用、响应禁止缓存，播放 URL 与 Token 不持久化、不写日志。
- HLS 仍只服务于 Backend ffprobe 和 AI Worker，M5 跌倒检测输入链保持不变。
- `ezuikit-js` 9.0.19 用于官方 EZOPEN Web 播放，许可证为 ISC；其解码静态资源在构建时从 npm 安装目录复制，不提交 Git。
- 当前实测 AI HLS 追到流尾后约有 6.2 秒媒体延迟；约 4 ms 的模型推理耗时不代表完整端到端延迟，后续实时告警阶段仍需优化媒体输入。

## M4 当前已完成内容

- Backend 与 AI Worker 共用唯一 `AlgorithmResult` 契约，score、task、level 和模拟标记均强校验
- 独立 AI Worker health、真实 capabilities、heartbeat 与统一 `ResultPublisher`
- 内部 Bearer 鉴权，Worker 短 TTL 和 Redis latest result TTL
- 单一 `/ws/realtime` envelope 与 Vue 集中式自动重连客户端
- `/algorithms` 显示真实 Worker、Redis、WebSocket 和未安装模型状态
- `/system` 显示真实 AI 基础设施状态
- 开发用 pipeline test 明确 `simulated=true`，不进入 Dashboard 或风险业务页面

架构、契约与安全策略见 [docs/ai-realtime-pipeline.md](docs/ai-realtime-pipeline.md)。

## M5 当前已完成内容

- AI Worker 通过内部鉴权向 Backend 获取临时 H6c HLS，不持有 EZVIZ Secret
- PyAV/FFmpeg 解码、可配置采样和自动重新获取临时地址
- YOLO26n-pose CUDA 推理与 CareShield 标准 Pose Schema
- 归一化姿态特征、持续时间状态机和明确的 heuristic score
- `fall_detection` 真实结果固定 `simulated=false`，无人/故障不显示 Normal
- `/fall-detection` 真实 Worker/GPU/模型/状态/性能页面
- Dashboard 仅更新真实跌倒检测；跌倒风险和诈骗风险仍保持未接入

实现、安全、依赖许可证与安全测试原则见 [docs/m5-fall-detection.md](docs/m5-fall-detection.md)。

## 尚未实现

RTMP/HTTP-FLV、PTZ、截图、云录像、历史回放、双向语音、设备事件、ASR、跌倒风险评估、诈骗识别、正式事件/告警、用户系统、业务数据库表和 Nginx 访问链路均未实现。M5 跌倒检测只是工程 baseline，未经过临床验证；M4 pipeline test 仍只是明确标记的传输诊断。
