# 部署、运行与技术开发底稿

## 1. 部署边界

目标主机为 Ubuntu 22.04、Docker Engine/Compose v2；GPU验收机需 NVIDIA RTX 4090、可用驱动和 NVIDIA Container Toolkit。Node 20.19+/22.12+ 与 Python 3.11+用于宿主开发。模型、人体资产、运行环境、受试者视频和 Secret 均不进入 Git。

服务划分为 frontend、backend、redis、postgres、media-server、media-relay、ai-worker、fall-risk-worker、motionclip-worker、kinecal-risk-worker、fraud-worker和ollama。GPU缺失时可叠加 `docker-compose.cpu.yml`，但算法能力应显示 unavailable，不能自动宣称正常。

## 2. 配置

执行 `cp .env.example .env`，仅在被忽略的 `.env` 写真实 PostgreSQL密码、`AI_WORKER_SHARED_TOKEN`、EZVIZ AppKey/AppSecret和本机模型路径。EZOPEN必须在可信本机显式启用。MotionCLIP/KINECAL runtime、Whisper模型、YOLO/STGCN/GVHMR/SMPL资产按 README 路径准备并只读挂载。

成功标准：`git check-ignore -v .env` 有命中；`.env.example` 只有占位符；`git status --untracked-files=all` 不出现模型、runtime、数据和播放器构建资产。

## 3. 启动与验证

```bash
git submodule update --init --recursive
docker compose up -d --build
docker compose ps
```

成功后有健康检查的服务应显示 healthy，frontend监听5173，backend监听8000，其余算法端口仅在Compose网络。依次验证：

```bash
curl -f http://localhost:8000/api/health
curl -f http://localhost:8000/api/integrations/ezviz/status
curl -f http://localhost:8000/api/devices
curl -f http://localhost:8000/api/algorithms
curl -f http://localhost:8000/api/fall-risk/status
```

预期健康接口返回 `status=ok`；EZVIZ 状态为 configured/reachable；设备列表至少含一台脱敏显示的在线 H6c；算法状态由 TTL 内心跳聚合；跌倒风险状态分别报告 VisionMD/GVHMR/MotionCLIP/KINECAL，不得用单一 ready 掩盖部分不可用。

## 4. 页面验证

打开 `/dashboard` 检查 EZOPEN 首帧、声音和实时状态；打开 `/fall-detection` 检查真实分析帧、人物框、骨架和持续结果；打开 `/fall-risk` 用安全行走视频验证任务进度、产物和历史回看；打开 `/fraud-risk` 用授权正常/诈骗测试音频验证转写和证据；打开 `/events`、`/devices`、`/algorithms`、`/system` 检查数据一致性。自动化只能验证首帧事件，真实摄像画面必须人工确认。

## 5. 测试命令

```bash
python -m pytest backend/tests
python -m pytest ai-worker/tests
PYTHONPATH=shared/python:fall-risk-worker python -m pytest fall-risk-worker/tests
PYTHONPATH=motionclip-worker python -m pytest motionclip-worker/tests
PYTHONPATH=kinecal-risk-worker python -m pytest kinecal-risk-worker/tests
PYTHONPATH=shared/python:fraud-worker python -m pytest fraud-worker/tests
python -m pytest media-relay/tests
cd frontend && npm test && npm run build
```

成功标准是全数通过、无测试删除/跳过、build退出码0。Rollup大chunk提示属于已知优化项，不等于构建失败。

## 6. 停止与故障排查

用 `docker compose down` 停止服务；不要加 `-v`，否则会删除 PostgreSQL、Redis、Ollama、风险评估和媒体卷。故障排查顺序为：Compose健康→Backend health→EZVIZ status/device online→media-relay ready→Worker heartbeat→latest result→WebSocket→页面console。日志只查看错误摘要，禁止复制完整临时流地址、Token或对话。

常见情况：设备离线时 Backend仍应健康；media-relay重连时实时AI显示 unavailable而不是normal；`warming_up`需约2秒连续可靠姿态；风险视频全身不可见或有效段不足会失败/复核；Fraud Worker音频重连、ASR/LLM不可用需分别显示；算法管理偶发 Not Installed 应先检查 TTL 心跳和 Backend聚合，而不是修改页面假定状态。

## 7. 开发约束

新增设备走 Adapter，模型推理留在独立 Worker，跨服务结构只在 `shared/python/careshield_contracts`定义。临时流不进入结果合同。修改后按影响范围运行测试；模型名称、版本、checksum、输入shape和阈值必须同步文档。任何训练/评估结果需同时保存配置、数据划分、逐样本预测和复算命令。
