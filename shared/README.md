# Shared Contracts

该目录保存跨模块共享的 API schemas、event contracts 和 algorithm result contracts。

M4 在 `python/careshield_contracts/` 中定义 Backend 与 AI Worker 唯一共用的
`AlgorithmResult`、Worker heartbeat 和 realtime envelope。契约不依赖 FastAPI、Redis、
传输协议或具体模型框架。测试链路结果必须使用 `task=pipeline_test` 且
`simulated=true`，不得进入风险业务页面。

M5 沿用同一个 `AlgorithmResult`，真实跌倒检测必须使用 `task=fall_detection`、
`simulated=false`。Worker heartbeat 增加框架无关的 runtime metadata 和能力生命周期，
前端仍不依赖 Ultralytics、PyTorch 或具体模型对象。
