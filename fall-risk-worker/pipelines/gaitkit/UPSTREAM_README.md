# Gaitkit

Gaitkit 从一段普通 RGB 视频中提取连续行走片段，经 GVHMR 恢复全局 SMPL-X 人体参数和世界坐标三维骨架，再由 GaitTransformer 估计步态相位、解码脚跟着地（HS）与脚尖离地（TO）事件，最终计算 **8 项核心时空参数和 20 项扩展参数**。本版本只生成数值结果，不进行人体网格或骨架视频渲染，也不包含分类模型。

完整处理顺序如下：

```text
整段 RGB 视频
    ↓
连续行走片段筛选与 30 Hz 时间归一化
    ↓
GVHMR 全局 SMPL-X 时间序列
    ↓
SMPL-X 关节回归与世界坐标三维骨架
    ↓
GaitTransformer 步态相位估计
    ↓
左右 HS 与 TO 事件
    ↓
28 项步态参数
```

## 1. 使用前需要准备什么

需要一台支持 CUDA 的计算机、待分析的视频、受试者实测身高，以及两个外部研究项目。建议分别准备三个 Python 环境，以避免 GVHMR 的 PyTorch 依赖与 GaitTransformer 的 TensorFlow、JAX 依赖发生冲突。

| 环境 | 用途 | 主要依赖 |
|---|---|---|
| Gaitkit | 视频筛选和流程调度 | NumPy、SciPy、OpenCV |
| GVHMR | SMPL-X 与全局运动恢复 | 按 GVHMR 官方说明安装 |
| GaitTransformer | 相位估计及 HS、TO 解码 | TensorFlow、Keras、JAX |

需要配置的外部项目为：

- [GVHMR](https://github.com/zju3dv/GVHMR)，包括其检查点和 SMPL-X 模型文件；
- [GaitTransformer](https://github.com/IntelligentSensingAndRehabilitation/GaitTransformer)，确认 `gait_transformer/assets/model_v0.2.h5` 存在。

程序默认视频中只有一名主要受试者，摄像机固定，受试者能够连续行走至少 3 秒。手持或移动摄像机也可以处理，但必须在配置中关闭固定摄像机选项，使 GVHMR 估计相机运动。

## 2. 安装与配置

在 Gaitkit 目录运行：

```bash
python -m pip install -e .
gaitkit init
```

`gaitkit init` 会生成 `gaitkit.toml`。打开该文件，确认 GVHMR 仓库、GaitTransformer 仓库以及两个模型环境的 Python 位置。

```toml
[tools]
gvhmr_root = "third_party/GVHMR"
gait_transformer_root = "third_party/GaitTransformer"
gvhmr_python = ".venv-gvhmr/bin/python"
visionmd_python = ".venv-visionmd/bin/python"
gvhmr_entry = ""
```

配置中的相对路径以 `gaitkit.toml` 所在目录为基准。Windows 环境可将解释器写为对应环境下的 `Scripts/python.exe`。配置完成后运行：

```bash
gaitkit check
```

检查通过后即可处理视频。

## 3. 最简单的用法

处理单个视频：

```bash
gaitkit run walk.mp4 --height-mm 1680
```

处理同一名受试者的一组视频：

```bash
gaitkit run videos --height-mm 1680
```

如果文件夹包含不同受试者，应提供身高表：

```csv
video,height_mm
subject_001.mp4,1680
subject_002.mp4,1540
```

然后运行：

```bash
gaitkit run videos --height-csv heights.csv
```

所有成功片段会汇总到：

```text
outputs/gait_metrics_28_all.csv
```

该表每行对应一个行走片段，前两列为视频内容编号和片段编号，后续 28 列为步态参数。每个片段还会保留一份带中文名、单位和计算定义的纵向参数表。

## 4. 输出文件

```text
outputs/
├── gait_metrics_28_all.csv
└── video_<内容编号>/
    └── segment_001/
        ├── input_30hz.mp4
        ├── hmr4d_results.pt
        ├── smplx_global_params.npz
        ├── world_skeleton_21.npz
        ├── gait_transformer_input_h36m17.npz
        ├── gait_events.csv
        └── gait_metrics_28.csv
```

`input_30hz.mp4` 是从原视频选出的连续行走片段，只进行时间截取和恒定帧率转换，不是渲染视频。`smplx_global_params.npz` 保存逐帧人体姿态、形状、全局朝向和全局平移。`world_skeleton_21.npz` 保存 H36M-17 骨架及左右足尖、左右足跟，共 21 个世界坐标关节。`gait_events.csv` 保存左右 HS、TO 的秒级时刻。最终结果是 `gait_metrics_28.csv` 和批量汇总表 `gait_metrics_28_all.csv`。

## 5. 各阶段的实现方法

### 5.1 连续行走片段筛选

程序先读取视频帧率、分辨率和帧数，再在缩小后的图像上计算人体出现情况与相邻帧变化。活动阈值根据当前视频的背景变化水平自适应确定，短时间漏检可在 1 秒内连接，连续时间少于 3 秒的区间被舍弃。该过程的作用是从较长视频中找到可能包含完整步行过程的连续片段，并不在像素阶段判断 HS 或 TO。

选中的区间会按真实时间轴重新写成恒定 30 Hz 视频。高帧率视频按时间位置抽帧，低帧率视频按时间网格重复最近帧，使后续帧序号能够稳定换算为秒。默认的运动检测方式无需额外模型；复杂背景下可以在配置中启用 YOLO，只用它提供更稳定的人体框，片段合并方法不变。

### 5.2 全局 SMPL-X 恢复

GVHMR 对 30 Hz 行走片段执行人体跟踪、二维姿态估计和图像特征提取。固定摄像机直接使用固定相机旋转；移动摄像机先估计相机自身运动，再恢复人体相对于世界的运动。模型输出的主要变量包括 `body_pose`、`betas`、`global_orient` 和 `transl`，分别描述关节姿态、人体形状、全局朝向和世界平移。

Gaitkit 使用无渲染适配器调用这条推理链，只保存 `hmr4d_results.pt` 和数值化的 `smplx_global_params.npz`。因此不需要生成 SMPL-X 网格视频，也不会调用可视化渲染流程。

### 5.3 三维骨架构造

SMPL-X 参数本身不是三维关节坐标。程序在 GVHMR 环境中调用 SMPL-X 人体层，逐帧计算扩展关节位置，再按固定映射回归为 H36M-17 骨架，同时保留左右足尖和左右足跟。输出坐标单位为米，采用 Y 轴竖直的世界坐标系，并保留 GVHMR 的全局平移。

H36M-17 是 GaitTransformer 的规定输入，其中没有独立足尖和足跟点。附加的 4 个足部点保留在世界骨架中，用于完整记录足部几何信息；GaitTransformer 的 TO 并不是直接寻找足尖高度极值，而是由连续步态相位解码得到。

### 5.4 步态相位与事件解码

事件识别前，程序按固定顺序提取 H36M-17 关节，逐帧减去 17 个关节的质心，再将 GVHMR 的 Y 轴竖直坐标转换为 GaitTransformer 使用的坐标约定。这个中心化副本只用于相位估计；步长、步速、步宽和稳定性等空间参数仍使用原始米制世界骨架。

GaitTransformer 以 60 帧，即 2 秒窗口估计连续步态相位。相位输出经状态空间平滑后，解码为左 HS、右 HS、左 TO 和右 TO 的时间序列。事件时间保留为秒，并允许落在相邻视频帧之间，以减少整帧取整造成的时间误差。

### 5.5 步态参数计算

时间参数由 HS、TO 的间隔计算；空间参数先在事件时刻对世界骨架做线性插值，再测量相应位移、角度或稳定性量。因此，GaitTransformer 决定事件发生的时间，GVHMR 世界骨架提供事件发生时的三维位置。

## 6. 28 项步态参数

| 序号 | 参数 | 单位 | 计算含义 |
|---:|---|---|---|
| 1 | 步频 | steps/min | 60 除以平均交替步时 |
| 2 | 步时 | s | 相邻左右 HS 的平均时间差 |
| 3 | 跨步时间 | s | 同侧连续 HS 的平均时间差 |
| 4 | 支撑时间 | s | 同侧 HS 到随后 TO 的时间 |
| 5 | 摆动时间 | s | 同侧 TO 到下一次 HS 的时间 |
| 6 | 双支撑时间 | s | HS 后到对侧 TO 的双脚接触时间分量 |
| 7 | 步长 | m | 相邻交替 HS 之间骨盆沿行进方向的位移 |
| 8 | 步速 | m/s | 平均步长除以平均步时 |
| 9 | 步宽 | m | HS 时左右踝沿横向轴的距离 |
| 10 | 摆臂幅度 | m | 手腕相对骨盆沿行进方向的峰峰值 |
| 11 | 抬脚高度 | m | 同侧 HS 周期内踝部最高点相对周期端点的高度 |
| 12 | 步时标准差 | s | 交替步时的样本标准差 |
| 13 | 跨步时间标准差 | s | 左右跨步时间合并后的样本标准差 |
| 14 | 步时变异系数 | % | 步时标准差除以平均步时 |
| 15 | 跨步时间变异系数 | % | 跨步时间标准差除以平均跨步时间 |
| 16 | 步长变异系数 | % | 步长标准差除以平均步长 |
| 17 | 步宽变异系数 | % | 步宽标准差除以平均步宽 |
| 18 | 步时对称指数 | % | 左右平均步时差相对于左右均值的百分比 |
| 19 | 躯干前倾角 | degree | 肩中点至骨盆向量偏离世界竖直轴的平均角度 |
| 20 | 髋角不对称 | degree | 左右髋屈曲角差的平均绝对值 |
| 21 | 膝角不对称 | degree | 左右膝角差的平均绝对值 |
| 22 | 髋膝综合不对称 | degree | 髋角与膝角不对称的平均值 |
| 23 | 估计质心横向摆动 | m | 髋中点近似质心的横向去均值均方根 |
| 24 | 外推质心横向摆动 | m | 质心位置与速度共同形成的横向均方根 |
| 25 | 最小稳定裕度 | m | 支撑边界到外推质心横向距离的最小值 |
| 26 | 平均稳定裕度 | m | 支撑边界到外推质心横向距离的平均值 |
| 27 | 髋宽归一化最小稳定裕度 | hip-width | 最小稳定裕度除以平均髋宽 |
| 28 | 髋宽归一化平均稳定裕度 | hip-width | 平均稳定裕度除以平均髋宽 |

## 7. 在 Python 中调用

```python
from gaitkit.settings import load_settings
from gaitkit.workflow import GaitkitWorkflow

settings = load_settings("gaitkit.toml")
workflow = GaitkitWorkflow(settings)
summary = workflow.run("walk.mp4", height_mm=1680)
print(summary)
```

查看五个处理阶段的输入和输出：

```bash
gaitkit describe --json
```

运行不依赖模型权重的基础测试：

```bash
python -m pytest
```

第三方代码、权重及人体模型文件的许可与引用要求见 `THIRD_PARTY.md`。
