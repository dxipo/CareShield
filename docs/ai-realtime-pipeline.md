# M4 — AI Realtime Pipeline

M4 建立与模型实现无关的统一实时结果链路，不包含任何真实 AI 推理：

```text
AI Worker
  -> ResultPublisher
    -> POST /internal/ai/results
      -> Redis latest state (TTL)
        -> /ws/realtime
          -> Vue RealtimeClient
```

Worker heartbeat 使用同一内部安全边界写入 `ai:worker:<worker_id>`，并设置短 TTL；
Worker 停止后状态会自动过期，不会永久显示 Online。最新结果使用
`ai:latest:<task>:<device-hash>` 并设置 TTL。M4 不引入 Kafka、RabbitMQ 或复杂队列。

## AlgorithmResult

唯一 Python 契约位于 `shared/python/careshield_contracts/algorithm.py`。核心字段为：

- `result_id`、`task`、`model_id`、`model_version`
- `device_id`、`source_timestamp`、`result_timestamp`
- `label`、可空且范围为 0–1 的 `score`、可空 `level`
- 可空 `latency_ms`、JSON `metadata`、必填 `simulated`

当前 task 仅允许 `fall_detection`、`fall_risk`、`fraud_detection` 和
`pipeline_test`。风险等级仅允许 `normal`、`low`、`medium`、`high`、`critical`。
任何 pipeline test 都必须 `simulated=true`。

## Worker 与内部鉴权

AI Worker 只通过 `ResultPublisher` 调用 Backend。`/internal/ai/*` 使用本地
`AI_WORKER_SHARED_TOKEN` 的 Bearer 鉴权；该 token 不返回浏览器。开发测试 endpoint
仅在 `APP_ENV=development` 时注册，生产环境不会暴露。

Worker capabilities 在 M4 均为 `not_installed`。Heartbeat 默认每 10 秒发送一次，
Backend 默认使用 30 秒 TTL。

## WebSocket envelope

Backend 只对浏览器提供一条 `/ws/realtime`：

```json
{
  "type": "algorithm_result",
  "timestamp": "2026-08-16T12:00:00Z",
  "data": {}
}
```

`type` 当前为 `algorithm_result` 或 `worker_status`。Frontend 的 `RealtimeClient`
集中处理连接、解析、指数退避重连和销毁，不在页面中散落 WebSocket 实现。

## Pipeline test policy

运行中的开发容器可执行：

```bash
docker compose exec ai-worker python -m app.test_publish
```

结果只显示在 `/algorithms` 开发诊断区和系统实时状态中，不得更新 Dashboard 风险卡、
事件中心、风险历史或任何业务结果。

## 安全边界

- Worker token 仅在被 Git 忽略的 `.env` 中配置。
- EZVIZ AppSecret、AccessToken 和临时 playback URL 不进入 AI contract。
- 内部 HTTP 客户端不继承宿主机代理，避免容器内部请求被错误转发。
- 日志不得打印 token、第三方凭据或结果中的敏感媒体地址。
