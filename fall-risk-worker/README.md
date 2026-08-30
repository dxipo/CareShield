# CareShield Fall Risk Worker

独立批处理 Worker，负责步态评估视频采集、VisionMD-Gait 28 项参数和 GVHMR
世界系 3D 骨架。它与实时跌倒检测 `ai-worker` 使用不同 Python/模型环境，避免
TensorFlow、GVHMR 和实时 PyTorch 推理互相污染。

当前 Worker 已实现稳定任务合同、持久化 manifest、安全媒体获取、时间窗采集和
CLI Adapter。VisionMD-Gait 使用 `/opt/visionmd-env` 独立 TensorFlow/CUDA 环境，
源码位于 `/opt/visionmd-app`；GVHMR 使用只读挂载的 `/runtime/gvhmr-env` 独立
PyTorch/CUDA 环境。具备授权资产时，两个流水线分别输出 MeTRAbs 骨骼点视频，以及
GVHMR 的相机视角 SMPL-X、世界系 SMPL-X 和米制 3D 骨架。缺少任一必要资产时会明确
报告 `not_configured`，不会生成模拟风险结果。

最终跌倒风险模型尚未接入，因此所有评估均保持：

```text
risk_model_status = not_installed
risk_result = null
```

本地模型资产均位于 Git 忽略的 `models/fall-risk/`。MeTRAbs small 模型来自作者
官方短链，且仅允许非商业用途；GVHMR 与人体模型也有独立许可证限制。
