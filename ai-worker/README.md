# CareShield AI Worker (M4)

AI Worker 是独立、CPU-only 的实时结果发布服务。M4 不包含模型、推理、视频处理、
CUDA、PyTorch 或模拟业务预测。

当前提供：

- `GET /health`：Worker 进程健康状态。
- `GET /capabilities`：三个算法均真实返回 `not_installed`。
- 周期性 heartbeat：经 Backend 内部鉴权接口写入带 TTL 的 Redis 状态。
- `ResultPublisher.publish(result)`：未来所有模型共用的唯一结果出口。
- 开发环境 pipeline test：只发布 `pipeline_test`、`simulated=true` 的诊断结果。

开发环境可在运行中的容器内触发一次完整链路测试：

```bash
docker compose exec ai-worker python -m app.test_publish
```

Worker 内部端口不映射到宿主机。`AI_WORKER_SHARED_TOKEN` 只通过本地 `.env` 注入，
不得写入代码、日志或 API response。
