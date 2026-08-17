# CareShield AI Worker (M5)

AI Worker 是独立实时 AI 服务。M5 在保留 M4 heartbeat/统一发布接口的基础上，增加
真实 H6c H.265 解码、CUDA 姿态估计和时序跌倒检测；Backend 不加载模型。

当前提供：

- `GET /health`：Worker 进程健康状态。
- `GET /capabilities`：跌倒检测按实际生命周期返回 starting/running/unavailable；跌倒风险和诈骗识别仍为 `not_installed`。
- 周期性 heartbeat：经 Backend 内部鉴权接口写入带 TTL 的 Redis 状态。
- `ResultPublisher.publish(result)`：所有模型共用的唯一结果出口。
- 开发环境 pipeline test：只发布 `pipeline_test`、`simulated=true` 的诊断结果。
- `BackendMediaClient`：仅凭内部 token 获取设备和临时 HLS，不持有 EZVIZ Secret。
- `MediaReader -> FrameSampler -> PoseEstimator -> TemporalFallDetector`：真实结果固定 `simulated=false`。

开发环境可在运行中的容器内触发一次完整链路测试：

```bash
docker compose exec ai-worker python -m app.test_publish
```

Worker 内部端口不映射到宿主机。`AI_WORKER_SHARED_TOKEN` 只通过本地 `.env` 注入，
不得写入代码、日志或 API response。模型权重保存在根目录被忽略的 `models/`，播放
地址只保存在进程内。算法阈值是 M5 工程基线，不是临床参数。
