# 软件系统实现底稿

## 1. 用户侧核心流程

用户进入综合首页后，可查看真实在线设备数、实时 EZOPEN 画面、跌倒与诈骗实时状态、近七日风险事件趋势和最近事件。首页数值来自设备 API、算法聚合 API、Redis 风险事件和 WebSocket，不使用随机曲线。独立 `/monitor` 已从路由删除，直播集中到首页。

跌倒检测页面显示 Worker 输出的同一分析帧：人物框、COCO17 骨架、当前状态、Fall Score、人物存在、骨架置信度、分析帧率和耗时。确认按钮只确认当前告警，不修改模型输出。`warming_up` 表示尚在积累约2秒的连续可靠骨架，期间没有有效 score，不能解释为未跌倒。

跌倒风险页面要求姓名、性别、年龄、身高等受试者信息，支持摄像机采集和 MP4 导入。后台异步执行姿态质量检查、步态事件、28项参数、GVHMR、KINECAL和MotionCLIP。页面展示输入视频、原景人体网格、8项核心参数、全部参数、跌倒风险等级、运动功能分析与历史任务。任务 manifest 和产物存入 Docker volume，可跨容器重启回看；这不是集中式业务数据库。

诈骗页面显示监听状态、ASR/LLM运行状态、脱敏文本、证据强度和告警。事件中心只收录 `simulated=false` 的高风险生命周期事件，开发 pipeline test 不进入业务页面。

## 2. 模块协作逻辑

Frontend 不接触设备 Secret 和模型对象，只消费 CareShield Schema。Backend 是设备适配、安全边界、业务编排和实时分发中心，但不做视频或模型推理。媒体中继把一个上游会话扇出给多个算法消费者，避免 Worker 争抢流。各 Worker 采用独立镜像或外部只读 runtime，以隔离 PyTorch、TensorFlow、GVHMR、MotionCLIP和 ASR 的版本冲突。

Redis 承担短生命周期 Worker heartbeat、latest result、跌倒状态历史和风险事件列表；WebSocket承担 Backend 到浏览器的低开销实时推送。PostgreSQL 当前仅启动并健康，不参与业务流程。Docker Compose 管理网络、依赖、健康检查、模型/数据卷和 GPU 暴露。

## 3. 页面与数据来源

| 页面 | 主要数据源 | 数据性质 | 尚存边界 |
|---|---|---|---|
| `/dashboard` | devices、algorithms、events、EZOPEN | 真实设备/实时状态 | 直播内容仍需人工确认 |
| `/fall-detection` | preview MJPEG、AlgorithmResult、history | 真实算法；`simulated=false`过滤 | 性能未形成正式报告 |
| `/fall-risk` | assessment API/artifact proxy | 真实批任务和持久化文件 | 两模型跨域/临床校准不足 |
| `/fraud-risk` | Fraud Worker heartbeat/result | 真实音频链；无原始音频留存 | 准确率待补测 |
| `/events` | Redis risk events | 真实告警生命周期 | 非永久事件库，无处置闭环 |
| `/devices` | EZVIZ Open API | 真实设备，序列号脱敏 | 无PTZ/回放 |
| `/algorithms` | Backend聚合心跳 | 真实Worker状态；pipeline test为【模拟数据】 | 开发诊断痕迹不宜用于主展示 |
| `/system` | health/system API | 真实基础状态 | PostgreSQL只显示部署健康，不证明业务使用 |

## 4. 接口概要

公开业务接口包括健康、EZVIZ状态、设备列表/详情、标准流/浏览器播放会话/媒体信息、算法状态、跌倒检测历史与确认、风险事件、跌倒风险任务与产物。内部接口包括 AI result/heartbeat、媒体设备/临时流和 Worker 预览，统一使用 `AI_WORKER_SHARED_TOKEN` Bearer 鉴权。浏览器唯一实时通道为 `/ws/realtime`。

## 5. 未实现功能

用户与权限体系、短信/电话/微信通知、家属联系人、临床工作流、PTZ、云录像、历史回放、正式 PostgreSQL 事件表、Nginx生产访问链路和医疗器械级校准均未实现。风险事件目前只有页面展示和 Redis 短期记录，不能写成完整“自动处置闭环”。
