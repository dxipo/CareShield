# M6 — Fall Risk Foundation

## Scope

M6 将既有 `risk_firststage` 的两个研究链路接入 CareShield，但保持运行环境和结果语义隔离：

```text
H6c timed capture ----\
                       -> persisted assessment clip
Browser MP4 upload ---/       |-> VisionMD-Gait -> MeTRAbs -> Gait Transformer -> HS/TO -> 28 parameters
                              `-> GVHMR -> SMPL-X -> world-coordinate 3D skeleton -> MotionCLIP
```

本文件记录 M6 特征基础阶段当时的边界。随后 CARE-PD MotionCLIP 核心模型已按
[motionclip-fall-risk-integration.md](motionclip-fall-risk-integration.md) 接入；它仍不输出
未经临床标定的高中低等级，也不得把连续健康参考偏离度称为风险概率。

## Worker boundary

实时跌倒检测继续由 `ai-worker` 负责。步态风险评估使用独立
`fall-risk-worker`，原因是 VisionMD/MeTRAbs 与 GVHMR 的依赖、模型资产和批处理负载均与
YOLO + STGCN 实时链路不同。两个 Worker 只共享版本化数据合同和 Backend 内部鉴权，
不共享 Python 环境，也不直接持有 EZVIZ 凭据。

```text
Vue -> Backend Fall Risk API -> fall-risk-worker
                                  |-> Backend internal media API -> EZVIZ temporary stream
                                  |-> VisionMD CLI adapter
                                  `-> GVHMR CLI adapter
```

Worker 每次只运行一个评估任务，manifest、原始片段和派生产物写入专用 Docker volume。
历史 API 从这些 manifest 恢复任务，因而容器重启后仍可回看原始视频、处理视频、步态参数和
模型结果。临时播放地址不进入 manifest、结果合同、Redis 或日志；用户上传视频也不进入 Git。

实时跌倒检测继续显式请求低延迟 HTTP-FLV；M6 固定时长批处理采集显式请求 HLS。两者共用
StreamService 合同但不争用同一种实时传输会话，且批处理不需要承担 HTTP-FLV 的低延迟约束。

## Assessment contract

一次评估包含：

- 任务状态与阶段进度；
- VisionMD-Gait 和 GVHMR 两条链路的独立状态；
- 质量指标与不足原因；
- 按时间、空间、变异性、姿态、稳定性分组的 28 项步态参数；
- 可用的处理视频和世界系骨架产物描述；
- 明确为空的最终风险结果。

参数缺失使用 `null` 和原因说明，不补随机值。空间和稳定性参数属于单目研究估计，
不应直接解释为临床诊断。

## Official GVHMR assets

官方源码作为 `third_party/GVHMR` Git submodule 固定在 commit
`6ec3ca39336c50492c0fae65fba2fb831fc7d866`。初始化仓库时运行：

```bash
git submodule update --init --recursive
```

该源码许可证仅允许教育、研究和非营利用途，并要求衍生修改开源；商业使用需联系作者授权。
当前比赛研究用途仍应保留版权和论文引用，产品化前必须重新进行许可证审查。

官方公开 checkpoint 放在被 Git 忽略的：

```text
models/fall-risk/gvhmr/official-checkpoints/
├── gvhmr/gvhmr_siga24_release.ckpt
├── hmr2/epoch=10-step=25000.ckpt
├── vitpose/vitpose-h-multi-coco.pth
├── yolo/yolov8x.pt
└── dpvo/dpvo.pth          # optional for a static camera
```

这些大文件不得提交 Git。下载即表示接受各模型对应许可证，部署前还应记录文件 SHA-256。

本机使用的官方 HMR2 checkpoint 已通过 PyTorch 加载与 ZIP 完整性校验：

```text
hmr2/epoch=10-step=25000.ckpt
size 2709494041 bytes
SHA-256 2dcf79638109781d1ae5f5c44fee5f55bc83291c210653feead9b7f04fa6f20e
```

Worker 还会检查该官方对象大小，避免中断续传产生的拼接文件仅因“文件存在”而被误判为就绪。

GVHMR 官方明确要求用户分别注册 SMPL 和 SMPL-X 网站并接受许可证。以下文件必须由有权用户
手动放入，不提供自动绕过注册的脚本：

```text
models/fall-risk/gvhmr/body_models/
├── smpl/SMPL_NEUTRAL.pkl
└── smplx/SMPLX_NEUTRAL.npz
```

本机已由完成官网授权的用户提供 neutral 资产，实际加载校验为：

```text
SMPL_NEUTRAL.pkl
SHA-256 4924f235e63f7c5d5b690acedf736419c2edb846a2d69fc0956169615fa75688

SMPLX_NEUTRAL.npz
SHA-256 376021446ddc86e99acacd795182bbef903e61d33b76b9d8b359c2b0865bd992
```

这些哈希仅用于校验本机资产，不代表项目有权重新分发。缺少人体模型或独立 Python
runtime 时，Worker 健康检查仍正常，但 GVHMR capability 显示 `not_configured`。

为避免数 GB CUDA 运行环境占用 Docker 根分区并膨胀服务镜像，GVHMR 使用本地、Git
忽略的独立 runtime：

```bash
PIP_INDEX_URL=https://pypi.org/simple ./scripts/bootstrap_gvhmr_runtime.sh
```

生成的 `runtime/gvhmr-env/` 只读挂载到 `fall-risk-worker`，不进入 Git，也不与 M5 或
VisionMD 共用 Python 环境。固定推理依赖清单位于
`fall-risk-worker/pipelines/gvhmr/requirements.txt`；PyTorch 2.3.0 + CUDA 12.1 和
torchvision 0.18.0 使用校验过的本地官方 wheel。一次性安装容器才包含 C/C++ 编译工具，
最终 Worker 镜像不包含编译工具链。

官方源码的 `body_model.py` 含一个未使用的 `turtle.forward` 导入，会在 headless slim
容器中引入 Tk 依赖。项目不修改 submodule 工作树，而是在 Worker 镜像构建时删除这一行；
该变更不影响模型、权重或数值计算，并保证固定官方 commit 可被干净复现。

处理产物保持语义分离：VisionMD 的 `visionmd_overlay.mp4` 是原 17 点骨架视频；GVHMR
另行生成 `1_incam.mp4`（SMPL-X 相机叠加）与 `2_global.mp4`（世界系网格视角），不会
覆盖或冒充原骨架视频。

`/fall-risk` 独立保留原始评估视频、MeTRAbs 骨骼与步态事件视频、GVHMR SMPL-X 网格视频。
某条链路未完成时对应窗口显示明确 Empty State，不再用另一条视频替代。页面的历史记录可
主动切换当前评估，视频、28 项参数和 MotionCLIP 结果均跟随所选记录。Worker 在算法运行前
完整解码输入片段并检查媒体损坏诊断；VisionMD
完成后还会检查有效姿态、全身可见、插值占比和最大缺失间隔。损坏视频或插值主导的结果
不会进入 GVHMR。已生成的骨骼视频和可计算步态参数仍作为复核材料保留，页面明确标记
`Quality Review`；缺失参数保持 `null`，且不会生成 MotionCLIP 风险结论。

右侧 SMPL-X 窗口默认使用 `gvhmr_incamera`：保留原始场景背景，并在相机坐标中以不透明
SMPL-X 网格覆盖模型投影到的人物主体区域。由于单目人体恢复和网格贴合存在误差，轮廓外仍
可能残留原人物像素，因此该模式改善隐私呈现但不能视为严格匿名化。`gvhmr_global` 世界系
中性背景视图继续保留，作为三维动作连续性和坐标恢复的研究诊断视图。

本机已用真实 H6c H.265 行走片段完成端到端验证。5 秒片段归一化为 30 FPS 后得到：

```text
SMPL-X 相机视角     H.264, 1280x720, 30 FPS, 150 frames
SMPL-X 世界系视角   H.264, 1280x720, 30 FPS, 150 frames
世界系骨架          150 x 21 x 3, metres, all finite
SMPL-X 参数          global_orient/body_pose/transl, 150 frames, all finite
```

人工抽帧确认相机视角网格贴合真实行走人物，世界系视频包含连续人体网格运动。这是几何
恢复与渲染链路验证，不代表最终跌倒风险模型或临床有效性验证。

### GVHMR runtime dependencies and licenses

| 组件 | 固定版本 | 用途 | 许可证/注意事项 |
| --- | --- | --- | --- |
| PyTorch / torchvision | 2.3.0+cu121 / 0.18.0+cu121 | CUDA 推理 | BSD-3-Clause，含第三方 notices |
| GVHMR | commit `6ec3ca3` | 世界系人体运动恢复 | 仅教育、研究、非营利用途；商业使用需授权 |
| Ultralytics | 8.2.42 | GVHMR 人体跟踪预处理 | AGPL-3.0 或商业许可证 |
| PyTorch3D | 0.7.6 | 3D 几何与渲染依赖 | BSD-3-Clause |
| SMPL / SMPL-X | 用户授权取得的 1.1 neutral 资产 | 人体网格模型 | 对应 MPI/Max Planck 许可，不随项目分发 |

## Shared media and capture timing

M5 和 M6 不再分别向萤石申请并占用播放会话。`media-relay` 读取一次 HTTP-FLV，使用
PyAV 18 / FFmpeg 8 的 `hevc_mp4toannexb` 将真实 H.265 + AAC 包无解码转封装到
MediaMTX RTSP。MediaMTX
对多个 Worker 扇出，并将 2 秒 fMP4 分片保留 2 分钟。

评估点击时间写入 `created_at`。M6 等待采集时长和 3 秒分片收尾，再以该时间戳从内部
缓冲获取 MP4。内部读取额外包含 8 秒 HEVC 关键帧预卷，完整解码后裁掉预卷并规范化为
从点击时刻开始的 H.264/yuv420p 输入，避免 fMP4 从 GOP 中间截取造成绿色参考帧错误；预卷
不会进入最终产物或算法时间窗。`capture_started_at`、`capture_completed_at` 和
`processing_started_at` 分别表达采集窗口与后处理起点。详见
[`docs/media-relay.md`](media-relay.md)。

## VisionMD-Gait integration

`risk_firststage` 是用户既有研究工程而不是可拉取的 Git 依赖。M6 将执行所需的最小代码、
Gait Transformer 权重和 GPL-2.0 许可证保存在 `fall-risk-worker/pipelines/visionmd/`，
不复制原工程的 Django/Electron 业务壳，也不把其环境混入主 Backend 或实时 Worker。
独立环境暴露稳定 CLI：

```text
python run_rgb_to_28.py INPUT.mp4 --height-cm HEIGHT --output OUTPUT_DIR
```

Adapter 只接受约定产物：

- `gait_parameters_28.json`
- `gait_events.json`
- `visionmd_overlay.mp4`（MeTRAbs 17 点骨架处理视频）

Worker 镜像中的 `/opt/visionmd-env` 固定使用 Python 3.10、TensorFlow 2.17 和独立 CUDA
运行依赖；`/opt/visionmd-app` 保存执行代码。MeTRAbs SavedModel 来自作者官方
`https://bit.ly/metrabs_s`，短链实际指向 RWTH Aachen 作者服务器。官方说明该模型因训练
数据许可证仅限非商业用途。模型存放于 Git 忽略的
`models/fall-risk/visionmd/metrabs_local_s/`，运行时只读挂载，不在评估请求中下载。
本机下载归档大小为 344,181,307 bytes，SHA-256 为
`a1c5d020911b62598131a42c6a550aaa96abb346b43b4a341d9977942525dc4e`。
来源与运行接口以 [MeTRAbs 官方仓库](https://github.com/isarandi/metrabs) 和
[官方 API 文档](https://github.com/isarandi/metrabs/blob/master/docs/API.md) 为准。

TensorFlow 2.17 下对既有 Gait Transformer 做了两处不改变权重语义的建图兼容修复：动态
时间维使用 `tf.shape`，并以 legacy Keras 的 `Lambda + Concatenate` 替代 Keras 3
`keras.ops`。独立 GPU smoke test 已验证 5 秒、30 FPS、完整人体样例可得到 16 个 HS/TO
事件、28/28 个参数和 H.264 骨架处理视频。测试身高仅为工程参数，不作为真实受试者结果。

质量门禁同时记录有效姿态比例、全身可见比例、插值帧比例、最大缺失间隔、有效步数和参数
缺失数。没有可用完整人体时任务明确失败，不以插值、零值或“正常风险”掩盖。

上传或采集片段可能在人物进入前、离开后包含空画面，也可能在折返之间存在长时间无人区间。
VisionMD 首先从逐帧有效姿态掩码构建连续轨迹：不超过 0.75 秒的短暂检测丢失保留在同一
片段内，长空白用于分段，最终选取有效姿态帧最多且至少 2 秒的片段。首尾无人帧不参加质量
统计或插值，GVHMR 与 MotionCLIP 使用同一裁剪片段。最大连续缺失门限以秒表示（当前
baseline 为 1.00 秒），避免 15 FPS 与 24 FPS 视频使用相同帧数却产生不同实际门限。
有效步数少于 6 或部分统计参数不可计算会进入质量复核说明，但与 SMPL-X 输入可用性分开；
只有姿态连续性不足才阻止 GVHMR/MotionCLIP。该处理不会把多个不连续行走片段拼接成一段，
避免跨空白插值制造虚假步态。

缺少模型时页面明确显示 Setup Required。

## Current API

- `GET /api/fall-risk/status`
- `POST /api/fall-risk/assessments`
- `POST /api/fall-risk/assessments/upload`（原始 `video/mp4` body，最大 512 MB）
- `GET /api/fall-risk/assessments`
- `GET /api/fall-risk/assessments/{assessment_id}`
- `GET /api/fall-risk/assessments/{assessment_id}/artifacts/{artifact_id}`

Backend 代理 Worker 响应，不向浏览器暴露内部 token、播放地址或模型私有路径。

## Remaining work

1. 用更多真实 H6c 直线步态样本校验事件、28 项参数和质量阈值的场景适用性。
2. 评估 MeTRAbs/Gait Transformer/GVHMR 的研究许可证对比赛展示及后续产品化的影响。
3. 对已接入的 MotionCLIP 连续偏离度做独立跨域与临床校准；校准前保持 `risk_level=null`。
