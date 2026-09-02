# 图表与架构图绘制素材

## 1. 系统总体架构图

**建议标题：** 智安护居多模态居家安全系统总体架构。目的为说明从感知到应用的分层。节点：H6c；EZVIZ平台；设备/Stream Adapter；media-relay/MediaMTX；实时跌倒、风险评估、诈骗Worker；Backend；Redis；WebSocket；Vue。箭头强调视频、音频、任务和AlgorithmResult。PostgreSQL标为“基础设施预留，当前无业务表”。全部节点均有真实代码，通知平台应以虚线【规划功能】表示。

## 2. 软件系统架构图

**建议标题：** CareShield模块化Backend与独立算法服务。以容器边界画frontend、backend、redis、postgres、media-server、media-relay、五类Worker和ollama；标明内部Bearer、私有端口、只读模型卷与数据卷。强调Backend不加载AI、Worker不持有EZVIZ Secret。

## 3. AI实时推理架构图

**建议标题：** 统一实时算法结果管道。节点按`Worker→ResultPublisher→POST /internal/ai/results→Schema validation→Redis latest/history/events→RealtimeHub→/ws/realtime→RealtimeClient→页面`排列；heartbeat另一路写带TTL的worker key。输入为AlgorithmResult，输出为统一envelope。

## 4. 跌倒风险评估流程图

**建议标题：** 双模型跌倒风险与运动功能评估流程。输入分摄像机时间窗、MP4上传；汇合到媒体校验、连续人体段、VisionMD和GVHMR；世界骨架分支到KINECAL输出低中高，SMPL-X参数分支到MotionCLIP输出健康参考距离和8概念；28参数、质量、视频和两个结果汇合到assessment manifest与页面。

## 5. 实时跌倒检测流程图

**建议标题：** 基于人物检测、COCO17与STGCN-Extend的实时跌倒检测。节点：内部RTSP→H.265解码→15FPS采样→YOLO person与YOLO pose并行→融合/ID→2秒每人buffer→75观测重采样+25模型预测→`[N,1,100,17,2]`→二分类softmax→阈值/恢复窗口→告警latch→M4管道。突出无人/低置信不等于正常。

## 6. MotionCLIP运动功能评估流程图

**建议标题：** 基于MotionCLIP的神经退行性疾病相关运动功能评估。节点：GVHMR SMPL-X→axis-angle到rotation-6D→`[B,25,6,60]`→Transformer encoder→motion embedding；分支一与healthy reference算余弦距离，分支二用relative embedding与8组text prototype计算概念概率；Qwen只做受约束文字组织。

## 7. 诈骗识别流程图

**建议标题：** 隐私约束下的实时音频诈骗证据分析。节点：RTSP AAC→PyAV→16k mono PCM→RMS端点→Faster-Whisper→置信度门→60秒上下文→规则/关键组合与可选Qwen并行→证据衰减/滞回→四状态→脱敏摘要→M4。标出原始音频不落盘、LLM本地运行。

## 8. 萤石开放平台接入架构图

**建议标题：** EZVIZ设备与双媒体协议接入。AppKey/Secret只指向Token Manager；设备API映射为Device Schema。播放分支：EZOPEN→官方Web Player；HLS→ffprobe诊断；HTTP-FLV→共享中继→算法。临时URL不持久化，EZOPEN Token仅no-store会话。

## 9. 前后端数据交互图

**建议标题：** CareShield REST、任务与WebSocket交互。浏览器先REST取设备、快照、历史和评估任务；异步评估以POST创建、GET轮询、artifact proxy取视频；实时结果从Worker POST Backend，再WS推送浏览器。标明内部与公开API安全边界。

## 10. Docker部署架构图

**建议标题：** Ubuntu/RTX4090 Docker Compose部署。外部只开放5173/8000；内部网络连接Backend、Redis、MediaMTX和Worker；GPU连ai-worker、fall-risk相关模型、ollama；模型目录只读、fall-risk-data/recordings/redis/postgres/ollama为volume。CPU override用虚线注释“核心平台可启动，GPU算法可能unavailable”。

## 绘图统一规范

真实已实现节点用实线，已有实现但待充分实测用虚线边框，规划功能用浅灰虚线。敏感数据用锁图标；不要在图中放设备完整序列号、Token、URL或受试者信息。算法图必须写真实shape和模型名，不使用“多模态大模型”泛称。
