# AI Worker

该目录预留给独立 AI Worker。M0 不包含模型、推理、训练、模拟 AI 输出、CUDA、PyTorch 或 GPU 容器配置。

预留模块：

- `fall_detection/`：实时跌倒检测
- `fall_risk/`：跌倒风险评估
- `fraud_detection/`：诈骗风险识别
- `asr/`：语音识别
- `pose/`：姿态估计

未来 AI Worker 应通过明确的 API 或事件契约与 Backend 通信，不能把推理代码放入 FastAPI route。
