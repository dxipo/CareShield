# 算法技术细节底稿

## 1. 步态参数提取技术

步态评估接收 8–60 秒 MP4 或摄像机时间窗。MeTRAbs 以 `mpi_inf_3dhp_17` 骨架输出逐帧 3D/2D 关键点；系统先按有效人体帧划分连续片段，只桥接不超过 0.75 秒的短缺失，并选择有效帧最多且不少于 2 秒的片段。缺失点仅在选中连续段内部插值，首尾无人和长空白不参与计算。随后将骨架换序、以人体中心归一化并转换坐标轴，Gait Transformer 产生步态相位/stride signal，Kalman 平滑后提取左右 heel strike 和 toe off，再计算参数。

当前参数合同真实包含 28 项：步频、平均步时、平均跨步时间、平均支撑时间、平均摆动时间、平均双支撑时间、估计步长、估计步速、估计步宽、摆臂幅度、左右足清障高度、步时/跨步时间标准差及变异系数、步长/步宽变异系数、左右步时对称指数、躯干倾斜、髋/膝/髋膝综合不对称、eCOM 与 XCoM 横向 RMS、最小/平均 eMOS 和髋宽归一化 eMOS。UI 只突出 8 项，不等于算法只计算 8 项。空间和稳定性值来自单目 3D 估计，应称“研究估计量”。

步时来自相邻脚跟着地事件的帧差除以 FPS；步频由 `60/平均步时` 得到；步长取相邻异侧 heel strike 时踝点前进方向间距，步速由步长/步时估计；支撑、摆动和双支撑时间由 HS/TO 配对获得。对称指数、变异系数和标准差描述周期稳定性。eCOM 由分段质量近似估计，XCoM 在 eCOM 基础上加入速度和倒立摆频率，eMOS 计算 XCoM 到接触支撑边界的最小距离。这些量为模型和专业人员提供时序、空间、姿态与稳定性四类证据。

#### 实现依据

- `fall-risk-worker/pipelines/visionmd/run_rgb_to_28.py`
- `fall-risk-worker/pipelines/visionmd/backend/app/analysis/signal_analyzers/gait_parameters_28.py`
- `fall-risk-worker/app/services/parameter_catalog.py`

## 2. 基于 MotionCLIP 的神经退行性疾病相关运动功能评估技术

当前代码真实使用 CARE-PD 扩展的 MotionCLIP encoder-only 架构，并加载部署者提供、Git 忽略的 checkpoint。输入不是 RGB，也不是文本，而是 GVHMR 输出的 `global_orient/body_pose/transl`。适配器将根关节和 21 个 SMPL-X body joints 转为 rotation-6D，为两个未提供的终端手部关节填充 identity rotation，并加入相对平移通道，形成 `[B,25,6,60]`、30 FPS、2 秒窗口、1 秒步长的 motion sequence。

Transformer encoder 以动作序列产生归一化 embedding。模型保存训练期健康参考向量，输出 `1-cosine(embedding, healthy_reference)`；该值是健康参考距离，不是疾病概率。embedding 与健康参考的差向量经八个 concept projector 和 checkpoint 中的文本 prototype 得到步幅、行走速度、足部抬升、摆臂、步频、步宽、横向稳定性和弯腰姿态的等级概率。现有推理代码不在运行时编码自然语言 Prompt；“文本语义”来自 checkpoint 内保存的 prototype。最终低/中/高分区使用训练集阈值 0.0206183 和 0.0557091，仅表示参考偏离区间。

模型级可解释性是“运动 embedding 与健康参考/概念文本 prototype 的关系”；系统级可解释性则来自 28 项参数、八项概念和质量信息的共同呈现。本地 Qwen3 只把既有数值组织为中文说明，不参与分级，也不得改变结果。因此正式名称必须统一为“基于 MotionCLIP 的神经退行性疾病相关运动功能评估技术”，不能写成阿尔茨海默病、帕金森病诊断或疾病风险预测。

#### 实现依据

- `motionclip-worker/app/model_runtime.py`
- `motionclip-worker/app/input_adapter.py`
- `motionclip-worker/app/model_service.py`
- `motionclip-worker/config/carepd_encoder_only_risk_thresholds.json`

## 3. 跌倒风险评估技术

当前承担正式页面跌倒风险等级的是 KINECAL 迁移模型，不是 Uni-GCN，也不是 MotionCLIP。GVHMR 世界系骨架含 21 个关节，适配器映射为 H36M-17，胸点由左右肩中点构造；坐标从 `X-forward/Y-left/Z-up` 变换为近 Kinect 轴，按骨盆中心化、尺度标准化并均匀采样至 120 帧，最终张量为 `[N,3,120,17,1]`。

网络是 ST-GCN++ encoder：H36M-17 图包含自连接、向心和离心三个邻接子集，十个时空图卷积块在空间骨架图上聚合关节信息，并以多尺度时间卷积分支建模不同时间感受野。全局池化后的 256 维特征与标准化视频时长拼成 257 维向量，再结合 `3m-walk-Front-View` 动作 embedding，经 action adapter 和三分类 head 输出 NF、FHs、FHm logits。当前分别映射为 low、medium、high，之后应用配置中的 action scale/bias 校准并 softmax。低于 0.55 置信度标为 review。

这一输出表达与 KINECAL 无跌倒史、单次跌倒史、多次跌倒史队列的相对分类，不是个体未来跌倒概率。代码没有把 28 项步态参数数值与 ST-GCN++ logits 融合；两者在页面层共同提供结构化证据。训练损失未包含在 CareShield inference-only 代码和 checkpoint 配置中，【待确认】原训练仓库后方可正式描述。

#### 实现依据

- `kinecal-risk-worker/app/input_adapter.py`
- `kinecal-risk-worker/app/model_runtime.py`
- `kinecal-risk-worker/app/model_service.py`
- `kinecal-risk-worker/config/kinecal_walk_v2.json`

## 4. 实时跌倒检测技术

实时链从共享 RTSP 解码 H.265 画面，目标采样率为 15 FPS、推理输入边长 960。YOLO26s 独立执行 COCO person 检测，YOLO26m-pose 输出 COCO17；二者按 IoU、包含率和中心距离融合。独立人物框使横卧时姿态关键点丢失仍能显示人物存在。追踪器用 IoU和归一化中心距离维持 ID，允许最多 30 个缺失帧；单人场景还允许更大的瞬时中心位移。它是项目自有轻量关联器，不应写成 ByteTrack 或 DeepSORT。

每个 track 独立维护 2 秒时间戳缓存。每帧至少 6 个关键点达到 0.35 且平均置信度达标才算可靠；窗口可靠比例至少 80%。约 30 个真实观测经线性时间重采样到 75 个位置，坐标从 `[0,1]` 映射到 `[-1,1]`，低置信点置零，再追加 25 个占位帧，形成 `[N,1,100,17,2]`。STGCN-Extend 首先从指定 40 帧片段编码并预测后续 25 帧，再把 75 个观测与 25 个预测拼接，经过同一 ST-GCN++ backbone、全局池化和二分类 head输出 logits。

class-1 softmax 被命名为 `fall_score`，未做概率校准。当前 0.45–0.65 为疑似跌倒，达到 0.65 进入 FALLEN；一次判断已覆盖 2 秒窗口，故配置为一个窗口确认。恢复需要连续 5 个低分窗口。结果状态为 NORMAL、SUSPECTED_FALL、FALLEN、RECOVERING；warming_up、无人、低姿态置信度或媒体失败不等于 NORMAL。状态变化、固定 1 秒心跳或显著分数变化才发布，避免逐帧写 Redis/WebSocket。告警至少显示15秒，人工确认可立即关闭；未确认时需最短展示时间结束且回到NORMAL才自动关闭。

#### 实现依据

- `ai-worker/app/fall_detection/{person_detector,pose_estimator,fusion,tracking,sequence}.py`
- `ai-worker/app/fall_detection/stgcn_extend/`
- `ai-worker/app/services/fall_detection_service.py`

## 5. 诈骗识别技术

Fraud Worker 从内部 RTSP 只解码音轨，统一重采样为 16 kHz mono PCM。能量端点器以 RMS 180 为默认阈值，0.7 秒尾静音切句，接受 0.5–15 秒语句。Faster-Whisper 1.2.1 使用本地 CTranslate2 模型、中文、beam size 3、temperature 0；平均 `exp(avg_logprob)` 作为工程置信度，低于 0.50 或短于两个字符不进入风险分析。

检测器在 60 秒、最多 8 段的内存上下文中匹配凭据、转账、远控、冒充公检法、投资、保健品、退款中奖、亲属冒充和紧迫话术，并检查高危词对。少量普通话同音 ASR alias 只有与“告诉/发给/念给”等分享动作共现时才生效。可选 Ollama `qwen3:4b` 对有意义语句进行 JSON 复核，temperature 0、关闭 thinking；高置信可疑判断增加证据，明确正常判断只降低部分规则强度。证据经衰减和滞回生成 normal/suspicious/warning/critical，分数是 heuristic ensemble 强度，不是诈骗概率。

发布结果包含脱敏且限长的 transcript preview、证据类别、匹配词、LLM 是否使用和告警状态；原始音频不落盘，完整对话只保留在短时内存。当前无云端 LLM 调用。规则和 LLM 均有单元测试，但没有正式标注语料上的准确率证据。

#### 实现依据

- `fraud-worker/app/media/`
- `fraud-worker/app/asr/faster_whisper.py`
- `fraud-worker/app/detection/detector.py`
- `fraud-worker/app/llm/ollama.py`
