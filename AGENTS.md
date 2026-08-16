# AGENTS.md

## 项目用途

本项目是“颐安盾——多模态居家老人智能风险防控平台”（Elderly AI Safety Platform），服务于老年人跌倒风险评估、实时跌倒检测和诈骗风险识别研究。M0–M3.1 已完成基础工程、Web 平台、真实 EZVIZ 设备与媒体链；当前 M4 只建立独立 AI Worker、统一算法结果契约、Redis 状态和 WebSocket 实时通道，不实现真实 AI。

## 固定技术栈

- Frontend：Vue 3、TypeScript、Vite、Vue Router、Element Plus；存在真实图表数据需求时再使用 ECharts。
- Backend：Python、FastAPI、Uvicorn。
- AI Worker：M4 使用 Python + FastAPI/httpx 的 CPU-only 基础设施；后续模型阶段再评估 PyTorch，必须独立于 Backend。
- Infrastructure：PostgreSQL、Redis、Docker Compose；需要时再引入 Nginx。
- Video：M3 使用 EZVIZ 官方 HLS Player 与 ffprobe；后续 AI Worker 可使用 FFmpeg、PyAV。

未经项目负责人确认，不得随意替换或增加同类技术栈。

## 目录职责

- `frontend/`：用户界面与 API 调用，不包含 AI 推理和设备接入逻辑。
- `backend/`：API、业务服务、配置、数据契约及适配器入口，不在 route 中实现 AI 推理。
- `ai-worker/`：独立 Worker health、heartbeat 与统一结果发布；M4 不含模型或推理。
- `shared/`：跨模块 API schema、事件契约和算法结果契约说明。
- `infra/`：部署基础设施配置。
- `data/`：本地运行数据，数据文件不提交 Git。
- `models/`：模型权重，模型文件不提交 Git。
- `docs/`：项目文档。
- `scripts/`：可复用的开发与运维脚本。

## 开发约束

1. 所有新功能必须保持 `frontend`、`backend`、`ai-worker` 解耦。
2. 摄像头、萤石开放平台、视频处理和 AI 能力必须通过独立模块或 Adapter 接入，不能侵入业务层。
3. 禁止把密码、Token、AppKey、AppSecret 或其他 Secret 提交到 Git；敏感配置从 `.env` 读取。
4. 新增依赖前先判断是否确有必要，优先使用简单、可靠、易维护的实现。
5. 修改代码后必须执行对应测试和构建检查。
6. 不允许为了完成任务删除、跳过或弱化已有测试。
7. 不允许用静态假数据伪装真实 AI 输出；未实现能力应明确标记为未实现。
8. 不允许把 AI 推理代码写进 FastAPI route。
9. 保持模块化单体 Backend + 独立 AI Worker，不做无必要的微服务拆分。
10. 代码应简单、明确、可维护，不为“看起来完整”创建无实际用途的抽象。
11. 播放地址按临时敏感资源处理，不得持久化、完整记录日志或写入测试 fixture。
12. Browser 播放、Backend 媒体探测和后续 AI Worker 通过 Stream 契约解耦；不得把媒体请求逻辑直接写进 API route。
