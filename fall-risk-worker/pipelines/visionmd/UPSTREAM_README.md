# 单 VisionMD-Gait：RGB 视频到 28 项步态参数

跨项目调用、输出字段和后端服务接入方式见：

```text
F:\跌倒预防\双链路接口接入说明.md
```

本目录是一条独立的纯 VisionMD 链路，不使用 GVHMR、SMPL 或 SMPL-X：

```text
RGB 视频
→ MeTRAbs（17 关节相机坐标 3D 骨架）
→ VisionMD Gait Transformer v0.2
→ Kalman smoother
→ 左右 Heel Strike / Toe Off
→ 8 个核心参数 + 20 个扩展参数
```

## 目录

```text
VisionMD-Gait-Standalone-28/
├─ run_rgb_to_28.py                 # 单命令入口
├─ requirements-standalone.txt      # 最小依赖
├─ backend/                         # VisionMD 后端、模型和 28 项实现
│  └─ app/analysis/models/
│     ├─ gait_transformer/          # 已包含 Gait Transformer 权重
│     └─ metrabs_local_s/            # 首次运行后生成
└─ frontend/                        # 原 VisionMD 前端，命令行运行时不需要
```

28 项计算代码位于：

```text
backend/app/analysis/signal_analyzers/gait_parameters_28.py
```

## WSL2 环境

当前可使用 `visionmd_run` 环境。必要的核心版本为：

```text
Python 3.10
TensorFlow 2.17.0
TensorFlow Hub 0.16.1
tf-keras 2.17.0
NumPy 1.26.4
SciPy 1.12.0
setuptools 70.3.0
```

如需新建环境：

```bash
conda create -n visionmd_standalone python=3.10 -y
conda activate visionmd_standalone
pip install -r requirements-standalone.txt
```

## 运行

在Windows PowerShell中可以直接运行：

```powershell
& "F:\跌倒预防\VisionMD-Gait-Standalone-28\run_wsl.ps1" `
  -Video "F:\路径\步行视频.mp4" `
  -HeightCm 170 `
  -Output "F:\路径\visionmd_result"
```

在 WSL2 中：

```bash
cd "/mnt/f/跌倒预防/VisionMD-Gait-Standalone-28"

conda run -n visionmd_run python run_rgb_to_28.py \
  "/mnt/f/路径/步行视频.mp4" \
  --height-cm 170 \
  --output "/mnt/f/路径/visionmd_result"
```

第一次运行时，如果以下目录不存在：

```text
backend/app/analysis/models/metrabs_local_s/
```

程序会从 VisionMD 原代码使用的 `https://bit.ly/metrabs_s` 下载 MeTRAbs
SavedModel。下载完成后可离线重复使用。

## 输出

```text
visionmd_result/
├─ visionmd_poses.npz          # 2D点和MeTRAbs 17关节3D骨架
├─ visionmd_signals.npz        # 相位及髋膝足运动学时序
├─ gait_events.json            # 左右HS/TO事件帧
└─ gait_parameters_28.json     # 28项最终参数
```

`gait_parameters_28.json` 中的 `gait_parameters_28` 固定包含28个字段。

## 坐标和限制

- MeTRAbs原始坐标：X向图像右侧、Y向下、Z为相机深度，单位mm；
- 步长使用相邻交替HS时骨盆的相机深度变化；
- 步宽使用HS时左右踝横向距离；
- MeTRAbs-17没有独立足跟、脚尖和足底边界，抬脚高度及支撑域以踝点近似；
- eCOM、XCoM和eMOS是单目骨架研究估计值，不是测力台真值；
- 相机应固定，被试应沿相机光轴直线走近或走远；
- 建议视频至少包含6个有效步骤，并提供真实身高。

## 测试

```bash
python -m unittest discover -s backend/tests -p "test_gait_parameters_28.py" -v
```
