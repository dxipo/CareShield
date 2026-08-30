# MotionCLIP 跌倒风险核心模型接入

## 运行链路

```text
H6c clip -> VisionMD-Gait -> 28 gait parameters
         -> GVHMR -> SMPL-X global parameters
         -> MotionCLIP Worker -> healthy-reference distance + 8 gait concepts
         -> Fall Risk API -> Vue /fall-risk
```

MotionCLIP 使用独立 Python/CUDA 运行时并在服务启动时加载一次模型。特征
Worker 只把 assessment UUID 交给模型 Worker；两者通过只读共享 assessment
volume 交换 `smplx_global_params.npz`。模型 Worker 不接触 EZVIZ AppSecret、
AccessToken 或播放地址。

## 输入适配

- 目标输入：float32 `[B, 25, 6, 60]`，30 FPS，2 秒窗口，30 帧步长。
- GVHMR 根旋转加 21 个 SMPL-X body joint 映射到 SMPL joint 0–21。
- SMPL hand joint 22–23 使用 identity rotation，并在结果 metadata 明示。
- joint 24 保存窗口首帧相对位移 `[tx, ty, tz, 0, 0, 0]`。
- 整段步行沿用 MotionCLIP 正式评估脚本：窗口健康距离和概念概率等权平均。

## 输出语义

默认 profile 为 `carepd_four_dataset_explainable`。它输出：

- `healthy_distance`：`1 - cosine(z, healthy_reference)`，不是概率；
- 八项步态概念及各等级概率；
- `risk_level = null`。

该 checkpoint 的 `clinical_risk_calibrated=false`。CareShield 不设置自造阈值，
不显示低/中/高临床等级。结果仅供科研探索，不构成诊断或医疗建议。GVHMR
实时采集域与训练数据域仍可能存在 domain shift，需要后续独立验证和校准。

## 本机配置

在被 Git 忽略的 `.env` 中设置：

```env
MOTIONCLIP_CHECKPOINT_PATH=/absolute/path/to/MotionCLIP/exps/carepd_motionclip_encoder_only_reference_diff_ft/checkpoint_best.pth.tar
MOTIONCLIP_RUNTIME_ROOT=/absolute/path/to/MotionCLIP/.runtime/conda-env
MOTIONCLIP_PROFILE=carepd_four_dataset_explainable
MOTIONCLIP_DEVICE=auto
```

仓库不保存 checkpoint、运行环境或患者/设备数据。

## 依赖与许可证

| 组件 | 验收版本 | 用途 | 许可证/边界 |
| --- | --- | --- | --- |
| MotionCLIP | upstream commit `8eae36d` 上的 CARE-PD 扩展 | Transformer 编码架构与研究 checkpoint | 上游代码 MIT；CARE-PD 扩展和 checkpoint 的研究/数据许可需由项目方单独确认 |
| PyTorch | 2.5.1+cu124 | CUDA 模型推理 | BSD-3-Clause |
| NumPy | 1.23.5 | GVHMR 参数读取与窗口整理 | BSD-3-Clause |

CareShield 镜像只包含 checkpoint 匹配的 inference-only 网络定义；模型 checkpoint
和 6.5 GB PyTorch runtime 通过本机只读挂载提供，不进入仓库和 Docker build context。
