# 智安护居项目技术事实底稿

> 审计日期：2026-09-02。结论以当前 `m6-fall-risk-foundation` 工作区代码为准。该工作区含未提交的 KINECAL、M7 和页面修整改动，不能等同于远端已发布版本。

## 1. 审计口径

本文把状态分为【已完成并可验证】、【已有实现，但缺少充分实测】和【规划/预留功能，尚未真正实现】。代码、单元测试与既有验收记录共同构成证据；仅有页面、配置项或模型文件不能单独证明功能完成。模型权重和运行数据按设计被 Git 忽略，仓库中只能核实装载逻辑、合同和本机文件存在性，不能由此推出泛化性能。

## 2. 当前真实功能审计

| 功能 | 状态 | 前端入口 | Backend/算法入口 | 数据与真实性 | 主要证据 |
|---|---|---|---|---|---|
| 基础健康检查 | 【已完成并可验证】 | `/system` | `GET /api/health` | 真实进程状态 | `backend/app/api/health.py` |
| EZVIZ 设备查询 | 【已完成并可验证】 | `/devices`、首页在线数 | `/api/integrations/ezviz/status`、`/api/devices` | 真实 Open API；无 Mock 设备 | `backend/app/adapters/ezviz/`、`device_service.py` |
| H6c 浏览器直播 | 【已完成并可验证】 | `/dashboard` | `/api/devices/{serial}/browser-playback` | 真实 EZOPEN 会话；需人工看画面 | `DashboardLiveMonitor.vue`、`stream_service.py` |
| 媒体探测 | 【已完成并可验证】 | 媒体诊断历史实现 | `/media-info` | ffprobe 证明媒体可解码，不证明画面内容 | `media_probe_service.py`、`docs/ezviz-streaming.md` |
| 共享算法媒体入口 | 【已完成并可验证】 | 无直接入口 | media-relay `/stream` | HTTP-FLV 的 HEVC 经 PyAV 解码并低延迟编码为 H.264，AAC 转封装为内部 RTSP | `media-relay/app/services/relay.py`、`mediamtx.yml` |
| M4 实时结果管道 | 【已完成并可验证】 | 全局 RealtimeClient、`/algorithms` | `/internal/ai/*`、Redis、`/ws/realtime` | pipeline_test 明确 `simulated=true` | `shared/.../algorithm.py`、`realtime_store.py` |
| 实时人物检测与姿态 | 【已完成并可验证】 | `/fall-detection` 分析画面 | ai-worker | YOLO26s person + YOLO26m-pose，COCO17；真实流结果 `simulated=false` | `person_detector.py`、`pose_estimator.py` |
| 人物追踪 | 【已完成并可验证】 | 分析画面人物框 | ai-worker | IoU、中心距离和短时丢失容忍；不是 Ultralytics Track 模式 | `tracking.py`、`fusion.py` |
| 实时跌倒二分类 | 【已有实现，但缺少充分实测】 | `/fall-detection`、首页状态 | STGCN-Extend→M4 管道 | 真实实时推理已接通；缺跨受试者现场精度与告警时延统计 | `stgcn_extend/`、`fall_detection_service.py` |
| 跌倒告警确认 | 【已完成并可验证】 | `/fall-detection` | acknowledge API、内存 latch、Redis 事件 | 真实检测结果触发；无短信/电话 | `alert.py`、`fall_detection.py` |
| 视频步态参数 | 【已有实现，但缺少充分实测】 | `/fall-risk` | fall-risk-worker | MeTRAbs+Gait Transformer；28 项可计算，UI重点展示 8 项；场景样本不足 | `run_rgb_to_28.py`、`gait_parameters_28.py` |
| GVHMR/SMPL-X | 【已完成并可验证】 | `/fall-risk` 处理视频 | fall-risk-worker CLI | 既有记录证明真实 H6c 5 秒片段产生 150 帧骨架/网格 | `pipelines/gvhmr/`、`docs/m6-fall-risk-foundation.md` |
| KINECAL 跌倒风险分级 | 【已有实现，但缺少充分实测】 | `/fall-risk` 新结果区 | kinecal-risk-worker | ST-GCN++ 三分类代码与权重合同已接入；当前工作区未提交，跨域验证不足 | `kinecal-risk-worker/`、`kinecal_walk_v2.json` |
| MotionCLIP 运动功能评估 | 【已有实现，但缺少充分实测】 | `/fall-risk` | motionclip-worker | 真实 checkpoint 合同、健康参考距离、8 概念；不是疾病诊断 | `motionclip-worker/` |
| 诈骗识别 | 【已有实现，但缺少充分实测】 | `/fraud-risk`、首页、事件页 | fraud-worker | 真实 H6c 音频、Faster-Whisper、规则和可选 Qwen；缺正式准确率测试集 | `fraud-worker/app/` |
| 风险事件 | 【已有实现，但缺少正式持久化】 | `/events`、首页趋势 | `GET /api/events` | Redis 有界列表保存真实 fall/fraud 告警；非 PostgreSQL 正式事件表 | `realtime_store.py` |
| PostgreSQL 业务数据 | 【规划/预留功能，尚未真正实现】 | 无 | 仅 Compose 容器 | 未发现 ORM、SQL 或业务表 | `docker-compose.yml` |
| 用户、权限、通知、PTZ、回放 | 【规划/预留功能，尚未真正实现】 | 无 | 无 | 无真实实现 | README“尚未实现” |

## 3. 当前技术栈

前端使用 Vue 3.5、TypeScript、Vite 7、Vue Router、Element Plus 和 `ezuikit-js 9.0.19`，通过 REST 获取快照，通过单一 WebSocket 接收实时结果。Backend 使用 FastAPI、Uvicorn、HTTPX 和 Redis 异步客户端；ffprobe 仅用于低频媒体诊断。AI 侧按环境隔离为实时跌倒、批处理步态/GVHMR、MotionCLIP、KINECAL、诈骗识别和媒体中继服务。实际框架包括 PyTorch/CUDA、Ultralytics、PyAV、TensorFlow 2.17、MeTRAbs、GVHMR、Faster-Whisper、Ollama/Qwen3。

部署采用 Docker Compose。PostgreSQL 16 和 Redis 7 均定义了健康检查，但当前业务状态、latest result、worker heartbeat 和风险事件实际写入 Redis；PostgreSQL 尚未承载业务数据。目标设备是 EZVIZ CS-H6c，已记录媒体为 HEVC/H.265 1920×1080、约 15 FPS、AAC LC 16 kHz 单声道。

## 4. 真实系统数据流

设备控制链由 Backend 的 EZVIZ Adapter 获取并缓存 AccessToken，再查询设备和临时播放地址。浏览器通过专用 `no-store` 会话获得 EZOPEN 地址与运行期 Token，由官方播放器展示低延迟画面。服务端算法不消费私有 EZOPEN：Backend 请求临时 HTTP-FLV，media-relay 用 PyAV/FFmpeg 将 HEVC 解码并低延迟规范化为 H.264，AAC 转封装到 MediaMTX 内部 RTSP，实时跌倒 Worker、诈骗 Worker和批处理采集从同一路径读取。

实时跌倒结果与诈骗结果被标准化为 `AlgorithmResult`，经内部 Bearer 鉴权发送给 Backend。Backend 写入 Redis latest state，按规则保存事件和状态历史，并封装成统一 realtime envelope 广播给 `/ws/realtime`。Vue 的单例 RealtimeClient 负责解析、重连和页面状态更新。跌倒风险属于异步批处理：摄像机时间窗或上传 MP4 经 VisionMD/GVHMR 生成参数和世界骨架，再分别交给 KINECAL 与 MotionCLIP Worker。

## 5. 审计限制

当前会话无 Docker daemon 访问权限，未使用提权弹窗干扰运行系统；运行态复核标为【需要人工验证】。`data/`、`models/`、`runtime/` 内容被 Git 忽略，正式证据需另存脱敏截图、命令输出和带版本号的测试报告，不能只依赖本机 Docker volume。
