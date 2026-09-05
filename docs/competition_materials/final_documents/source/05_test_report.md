---
title: "智安护居——多模态居家老人智能风险防控平台"
subtitle: "实测数据与功能测试报告"
author: "学校—团队负责人姓名—手机号"
date: "2026年9月"
lang: zh-CN
toc-title: "目录"
---

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 目录

1. 测试目的与范围
2. 测试环境与方法
3. 本次工程测试结果
4. 真实设备与媒体测试
5. 实时跌倒检测测试
6. 跌倒风险与运动功能评估测试
7. 诈骗风险识别测试
8. 待补测实验设计
9. 功能测试结论
10. 待补充信息汇总

# 报告说明

本报告对应初审材料“05_测试报告”，记录智安护居（CareShield）V1.0 的工程测试、真实设备与媒体验证、算法链路验证和当前实验数据边界。测试基线为 Git 标签 `v1.0.0`、提交 `e8e474c`。报告只将可复核的命令输出、运行状态、模型产物和人工画面确认证据列为结果；单元测试通过不等同于算法准确率，训练集阈值、checkpoint 兼容性和单段视频 smoke test 不作为独立泛化性能。

| 项目 | 内容 |
|---|---|
| 测试对象 | CareShield V1.0 |
| 代码基线 | `v1.0.0` / `e8e474c` |
| 测试日期 | 2026年9月4日 |
| 主要设备 | EZVIZ CS-H6c-V200-8H8WFL |
| 部署方式 | Ubuntu 22.04 + Docker Compose |
| GPU | NVIDIA GeForce RTX 4090 |
| 证据口径 | 代码、测试输出、API、容器状态、脱敏产物与人工画面确认 |

# 1 测试目的与范围

测试围绕三个层次展开。第一层验证软件工程是否可部署、接口是否可调用、前后端是否连通、Redis 与 Worker 是否形成实时结果链；第二层验证真实 H6c 的设备、视频、音频和多消费者媒体链；第三层验证人物与姿态、实时跌倒、步态与人体运动恢复、跌倒风险研究分级和诈骗风险识别能否在当前部署中运行并输出结构化结果。

本报告不填补仓库中不存在的 Accuracy、Precision、Recall、F1、AUC 或临床结论。当前没有形成统一受试者隔离测试集、逐样本预测文件和完整混淆矩阵，因此算法准确性仍属于后续专项补测项目。本次测试结论限定为“工程链路可运行”和“指定真实样例产生预期类型输出”。

# 2 测试环境与方法

## 2.1 软硬件环境

| 类别 | 实际配置或版本 |
|---|---|
| 操作系统 | Ubuntu 22.04 目标部署环境 |
| 摄像机 | EZVIZ CS-H6c-V200-8H8WFL，当前 API 状态 Online |
| GPU | NVIDIA GeForce RTX 4090，实时 Worker runtime 为 `cuda:0` |
| 容器编排 | Docker Compose，共 12 个服务 |
| 前端 | Vue 3.5、TypeScript 5.8、Vite 7、Element Plus、ezuikit-js 9.0.19 |
| Backend | FastAPI 0.116.1、Uvicorn 0.35.0、HTTPX 0.28.1 |
| 实时 AI | PyTorch 2.13.0+cu130、Ultralytics 8.4.120、PyAV 18.1.0 |
| 实时存储 | Redis 7 Alpine，AOF 开启 |
| 数据库 | PostgreSQL 16 Alpine，当前无业务表 |
| 媒体服务 | media-relay + MediaMTX 1.20.0 |
| 本地语言模型 | Ollama 0.12.11，Qwen3 4B |

## 2.2 测试方法

工程测试使用 pytest、Vitest、Vue TypeScript 检查、Vite 生产构建、Docker 健康检查和 HTTP API 响应。真实设备测试通过萤石 Open API 返回、浏览器人工画面确认和 ffprobe 媒体元数据交叉验证。算法链测试区分三类证据：单元测试使用明确标记的 synthetic fixture；集成测试使用授权视频或 H6c 媒体；训练或历史项目输出只作为模型来源与兼容性证据。

实时性能数据取自 Worker 安全 runtime metadata，只记录观察时刻的遥测值，不计算均值或置信区间。需要统计意义的性能结论，必须按第 8 章方案重新采样。

# 3 本次工程测试结果

## 3.1 Docker 服务状态

2026年9月4日执行 `docker compose ps`，12 个服务均为 `Up`。其中定义健康检查的 10 个服务均为 `healthy`；frontend 与 media-server 未定义 Compose healthcheck，状态为 `Up`。

| 服务 | 运行结果 | 健康检查 |
|---|---|---|
| frontend | Up | 未定义 healthcheck |
| backend | Up | healthy |
| ai-worker | Up | healthy |
| fall-risk-worker | Up | healthy |
| motionclip-worker | Up | healthy |
| kinecal-risk-worker | Up | healthy |
| fraud-worker | Up | healthy |
| ollama | Up | healthy |
| media-relay | Up | healthy |
| media-server | Up | 未定义 healthcheck |
| postgres | Up | healthy |
| redis | Up | healthy |

结论：Compose 基础部署通过运行状态检查。该结果证明服务在线，不代替业务正确性和算法性能测试。

## 3.2 API 与真实设备状态

| 测试项 | 实际结果 | 判定 |
|---|---|---|
| `GET /api/health` | `status=ok`，`service=backend` | 通过 |
| `GET /api/system/status` | Backend online、Redis healthy、AI Worker online | 通过 |
| `GET /api/integrations/ezviz/status` | configured=true、reachable=true | 通过 |
| `GET /api/devices` | 发现 1 台 EZVIZ H6c，online=true | 通过 |
| `GET /api/algorithms` | fall_detection running、fall_risk installed、fraud_detection running | 通过 |

接口响应中未发现 AppSecret 或 AccessToken。测试记录不保存完整设备序列号和播放地址。

## 3.3 单元测试与前端构建

| 模块 | 命令或方式 | 本次结果 |
|---|---|---|
| Backend | `PYTHONPATH=shared/python .venv/bin/python -m pytest backend/tests -q` | 58 passed，0 failed |
| Fall Risk Worker | `PYTHONPATH=shared/python:fall-risk-worker ... pytest` | 36 passed，0 failed |
| Fraud Worker | `PYTHONPATH=shared/python:fraud-worker ... pytest` | 19 passed，0 failed |
| Media Relay | `PYTHONPATH=shared/python:media-relay ... pytest` | 5 passed，0 failed |
| KINECAL Worker | `PYTHONPATH=kinecal-risk-worker ... pytest` | 3 passed，0 failed |
| Frontend | `npm test` | 2 test files，5 passed |
| Frontend build | `npm run build` | 类型检查和生产构建成功 |
| AI Worker | 通用 `.venv` 不含其固定 torch/OpenCV | 本次未纳入 host pytest 汇总 |
| MotionCLIP Worker | 通用 `.venv` 不含其固定 torch runtime | 本次未纳入 host pytest 汇总 |

本次可重复执行并通过的测试合计为 126 项 Python 测试和 5 项前端测试。AI Worker 与 MotionCLIP 的容器健康检查通过且真实 runtime 在线，但没有在错误的通用 Python 环境中补装深度学习依赖来制造“全量 pytest 通过”。这两组测试需要在各自隔离开发环境中补跑并保存输出。

前端构建转换 1690 个模块并生成生产产物。构建存在两类非阻断 warning：`@vueuse/core` 中 PURE 注释位置被 Rollup 移除，以及 Dashboard 相关 chunk 超过 500 kB。构建最终状态为成功，warning 作为后续加载优化事项保留。

# 4 真实设备与媒体测试

## 4.1 H6c 设备接入

Backend 使用本机 `.env` 中的 AppKey/AppSecret 向萤石开放平台申请 Token，并查询标准化设备列表。本次运行态返回 configured=true、reachable=true，发现 1 台型号为 CS-H6c-V200-8H8WFL 的设备，状态 online。页面只显示脱敏设备标识。

结论：真实设备身份认证、设备列表和在线状态链通过。

## 4.2 浏览器实时视频

浏览器通过 Backend 的禁止缓存会话接口启动官方 `ezuikit-js` EZOPEN Player。既有人工验收已确认页面显示真实 H6c 画面和声音，并通过摄像机前物体移动验证内容变化；页面观察显示延迟明显低于早期 HLS 方案。当前没有以统一时钟、重复试验和分位数统计获得精确浏览器端到端延迟，因此报告不填写秒级结论。

真实性判据同时要求：播放器收到首帧、画面不是平台错误提示媒体、摄像机前运动能在页面中对应出现。仅 HTTP 200、readyState 或播放器 started 不判定真实画面通过。

## 4.3 媒体元数据

对真实 H6c 临时 HLS 地址的既有安全 ffprobe 记录如下。

| 媒体 | 字段 | 实测值 |
|---|---|---|
| Video | codec / profile | HEVC/H.265 Main |
| Video | resolution | 1920 × 1080 |
| Video | frame rate | 约 15 FPS |
| Video | pixel format | yuv420p |
| Video | bitrate | 未从本次 manifest/ffprobe 取得 |
| Audio | available | YES |
| Audio | codec | AAC LC |
| Audio | sample rate | 16000 Hz |
| Audio | channels | 1，mono |
| Audio | bitrate | 未取得 |

上述结果证明该播放会话包含可解码的真实视频和音频。媒体内容真实性另由人工画面确认承担，ffprobe 成功本身不等于摄像机内容已确认。

## 4.4 共享媒体中继

当前运行态中 media-relay、media-server、实时跌倒 Worker 和诈骗 Worker 均在线。算法 Worker 读取同一内部 RTSP，而不是分别打开 HLS；实时跌倒 runtime 报告 stream_status=connected，诈骗 runtime 报告 audio_status=connected。媒体中继已解决从 HEVC GOP 中间截取评估片段时出现绿色参考帧的问题，并向批处理提供按触发时间裁剪的 H.264/yuv420p MP4。

运行态累计 reconnect_count 较高，说明上游或内部读取存在频繁会话重建。当前服务能够自动恢复并保持 connected，但尚未形成连续 2 小时的重连原因分类、可用率和丢帧统计，不能据此宣称长时间稳定性已经验证。

# 5 实时跌倒检测测试

## 5.1 功能链验证

实时 Worker 运行状态显示人物检测模型 `yolo26s.pt`、姿态模型 `yolo26m-pose.pt`、分类器 `stgcn-extend-real440` 均已加载，设备为 `cuda:0`，GPU 名称为 NVIDIA GeForce RTX 4090。Worker 能发布 `task=fall_detection`、`simulated=false` 的结果，Backend、Redis、WebSocket 和前端能够接收。

页面人工测试已经覆盖人物框、COCO17 骨架、warming_up、normal、suspected_fall、fallen、恢复、红色告警与人工确认。warming_up 表示正在积累约 2 秒的连续可靠骨架，不是“正常”或“未跌倒”。横卧姿态关键点不足时，独立 person detector 仍保留人物存在信息；姿态不可靠时系统不生成 normal。

## 5.2 单点运行遥测

2026年9月4日运行态快照记录如下。数值是一个观察时刻的系统遥测，不是 benchmark 平均值。

| 指标 | 观察值 |
|---|---|
| source FPS | 15.167 |
| sampled FPS | 15.580 |
| processing FPS | 15.604 |
| person inference | 4.653 ms |
| pose inference | 6.224 ms |
| classifier inference | 6.600 ms |
| classifier frequency | 2 Hz |
| observation window | 2.0 s |
| sequence | 75 observed + 25 predicted = 100 |
| AI device | cuda:0 |

这组数据证明当前实例能以接近源帧率完成检测处理，分类器按 2 Hz 发布判定。它不包含摄像机采集、萤石平台、网络、中继缓冲、2 秒观察窗和浏览器呈现的全部延迟，不能直接写成端到端告警时间。

## 5.3 模型历史证据与限制

STGCN-Extend checkpoint 在保存的 88 样本 split 上重现 88/88，其中 34 段 fall、54 段 non-fall。该结果证明当前部署网络、预处理和权重相互兼容；由于测试 split 的受试者独立性、数据采集主体和外部场景覆盖证据不完整，不作为 CareShield 实时部署 Accuracy=100%。当前仓库未保存事件级 TP、FP、FN、每小时误报和漏报统计。

# 6 跌倒风险与运动功能评估测试

## 6.1 VisionMD-Gait smoke test

5 秒、30 FPS、全身可见样例通过 MeTRAbs 与 Gait Transformer，得到 16 个 HS/TO 事件、28/28 项参数和 H.264 骨架处理视频。该结果证明步态事件和参数计算接口可运行；单一样例不能证明 28 项参数的量测精度。真实折返、短片段、脚部遮挡和人物进出画面会减少可用事件，质量门禁会保留缺失字段而不补零。

## 6.2 GVHMR/SMPL-X 真实片段

既有真实 H6c 5 秒行走片段归一化为 30 FPS 后，产生 150 帧 SMPL-X 相机视角视频、150 帧世界系视角视频、`150 × 21 × 3` 世界骨架以及对应 SMPL-X 参数。两类视频为 H.264、1280×720、30 FPS，骨架和参数均为有限值。人工抽帧确认网格随行走人物连续运动。

该结果验证单目人体恢复、世界骨架导出和渲染产物链，不代表 SMPL-X 网格误差、步态参数误差或跌倒风险准确率。

## 6.3 KINECAL 跌倒风险分级

KINECAL Worker 当前 healthy，页面和任务编排已接入 ST-GCN++ 三分类。项目说明记录单一 3m walk held-out accuracy 为 74%，同时记录高风险类别 recall 为 0/7。由于原始逐样本评估 JSON、固定数据划分和复算脚本未随当前仓库形成完整证据链，本报告不把 74%列为系统正式准确率；高风险 0/7 明确表明当前迁移模型对该类的敏感性不足。

## 6.4 MotionCLIP 运动功能评估

MotionCLIP checkpoint 和 Worker 已接入，使用 SMPL-X 动作窗口计算健康参考距离和 8 项运动概念。阈值选择文件记录 141 段 walk、83 名受试者和 macro-F1 0.505334，该数值来自训练期阈值选择，不是外部独立测试。当前可验证结论限于模型输入适配、checkpoint 加载、结果合同和页面呈现；不能写成神经退行性疾病诊断准确率。

# 7 诈骗风险识别测试

Fraud Worker 当前 healthy，状态为 listening，音频 connected，SenseVoiceSmall ready，设备为 CPU，本地 Qwen3 4B ready。运行态已经持续处理真实 H6c 音频，并发布 `task=fraud_detection`、`simulated=false` 的结构化结果。页面人工测试覆盖正常语音、诈骗高风险话术、脱敏文本、LLM 使用标记、告警条幅和人工确认。

一个运行态样本记录 1.268 秒语句的 ASR 处理耗时约 48 ms，完整结果约 51 ms。该值只描述端点完成后的单次计算，不包括等待句尾静音、摄像机与网络传输，也不构成平均响应时间。

当前仓库没有正式标注的正常/诈骗语料、说话人隔离划分、逐样本预测与混淆矩阵，因此诈骗识别 Accuracy、Precision、Recall、F1、误报率和漏报率均未形成可引用结果。模板材料中出现的 240 条语料和 93.3%召回率不属于当前仓库证据，本报告不采用。

# 8 待补测实验设计

## 8.1 实时跌倒检测

采用取得书面授权的非老人安全演示参与者和公开合法测试视频，按受试者隔离训练、验证和测试。测试场景至少包含向前/向后/侧向跌倒、坐下、弯腰、下蹲、躺床、遮挡和多人。事件窗口定义为动作前 3 秒至倒地后 5 秒，记录事件级 TP、FP、FN 与非事件时长，报告 precision、recall、F1、每小时误报、漏报、首次告警时间 P50/P95、AI FPS 和连续 2 小时可用率。禁止要求老人执行危险跌倒。

## 8.2 跌倒风险评估

固定 subject-level 数据划分，对 KINECAL ST-GCN++、去除 action adapter 和仅步态参数分类器进行对比。每条记录保存匿名样本 ID、真实标签、三类分数和预测类别，报告 accuracy、macro precision/recall/F1、balanced accuracy、one-vs-rest AUC、95% bootstrap CI 与三类混淆矩阵。真实 H6c/GVHMR 域单独报告，不与训练数据混合。

步态参数需使用可追溯参考系统或人工标注校验 HS/TO、步数、步频、步时和步长误差。MotionCLIP 只评价运动功能表征与参考偏离的一致性，不以疾病诊断为终点。

## 8.3 诈骗识别

建立授权中文对话集，按说话人隔离，覆盖验证码、转账、公检法、亲属求助、投资、保健品、退款及相似正常对话。分别测试 ASR 文本、规则 only、规则+Qwen，报告 CER/WER、语句级和会话级 precision、recall、F1、每小时误报、漏报、端到端延迟 P50/P95。真实家庭敏感音频不得进入公共测试集。

# 9 功能测试结论

CareShield V1.0 在当前主机上完成 12 服务运行，Backend、Redis、AI Worker、设备接入和三个算法方向均可从 API 获得真实状态。真实 H6c 在线，EZOPEN 视频、H.265 视频元数据与 AAC 音频已经验证；实时跌倒、跌倒风险和诈骗识别均形成从媒体输入、独立 Worker、Backend、Redis/WebSocket 到页面的工程链路。

当前最充分的证据是系统可部署性、真实设备和媒体接入、模块接口、处理产物及实时运行遥测。算法的跨受试者准确率、误报率、漏报率、端到端响应分位数和长期稳定性证据不足，不能用单元测试和单样例结果替代。初审材料应据此把“已实现运行链路”和“待完成统计验证”分开呈现。

# 10 待补充信息汇总

提交前需要项目负责人补充以下内容：

1. 学校、团队负责人姓名、手机号和最终文件名。
2. 真实老人数据的受试者人数、年龄范围、与采集者关系、居家环境、采集协议、授权与匿名化记录。
3. 跌倒、非跌倒、诈骗、正常语音和跌倒风险标签的逐样本测试清单及混淆矩阵。
4. 统一时钟的浏览器视频延迟、算法端到端告警 P50/P95 和 2 小时稳定性原始日志。
5. AI Worker 与 MotionCLIP 隔离环境的完整 pytest 输出。
6. 固定 commit 的 `docker compose ps`、GPU、设备 Online、三条业务链和事件页面脱敏截图。
7. KINECAL 原始评估 JSON 与数据划分说明；没有回收前不引用 74%为正式结果。
