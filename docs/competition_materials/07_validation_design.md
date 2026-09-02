# 评委验证设计说明

| 验证项 | 前置条件与输入 | 操作 | 预期结果/通过标准 | 系统位置 |
|---|---|---|---|---|
| H6c接入 | `.env`有效、设备联网 | 调用status/list/detail | configured/reachable，发现在线H6c，页面序列号脱敏 | `/devices` |
| 实时视频 | 启用EZOPEN | 打开首页并在镜头前移动物体 | 首帧后LIVE；画面随动作变化；刷新和全屏退出正常 | `/dashboard` |
| 音频 | 摄像头有声 | 播放授权语音并开播放器声音 | 可听见声音；媒体探测显示AAC/16k/mono | 首页/`media-info` |
| 人物检测 | 人体全身入镜 | 站立、移动、横卧安全姿态 | 显示人物框；无人时不显示正常 | `/fall-detection` |
| Tracking | 单人连续移动/转身 | 横跨画面并短暂遮挡 | ID短时保持，重复框受抑制 | 分析预览 |
| 骨架识别 | 全身和关节可见 | 走动、弯腰、坐下 | COCO17连线随人体变化；低置信明确提示 | 分析预览 |
| 运动功能评估 | 8–60秒直线行走、受试者信息 | 摄像机采集或上传MP4 | 进度完成；输入/网格视频、参数、质量结果可回看 | `/fall-risk` |
| 跌倒风险 | GVHMR/KINECAL ready | 运行历史片段或新评估 | 输出三档、置信度和review；不得称概率 | `/fall-risk` |
| MotionCLIP运动功能 | MotionCLIP ready | 完成同一评估 | 输出健康参考距离、8概念和解释；不诊断疾病 | `/fall-risk` |
| 实时跌倒 | 安全演示视频，严禁老人危险动作 | 先正常后模拟倒地并保持 | warming约2秒；score和状态变化；连续确认后告警 | `/fall-detection` |
| 告警确认 | 已触发fallen | 点击确认 | 当前红色提示关闭；恢复正常后可重新布防 | 跌倒页 |
| 诈骗识别 | Fraud/ASR/可选Qwen ready | 播放正常和诈骗对照语音 | 显示脱敏文本、证据、风险；高危触发告警 | `/fraud-risk` |
| AI Worker | 全栈启动 | 查看算法管理/health | 心跳TTL内Online，三能力由全部Worker聚合 | `/algorithms` |
| Redis | Redis healthy | 发布结果后重载页面 | latest可恢复；过期Worker自动离线 | API/算法页 |
| WebSocket | 页面打开 | 暂停/恢复Backend网络 | connected→reconnecting→connected，无重复连接 | 页面状态 |
| 事件页 | 真实fall/fraud告警 | 打开事件页 | 只出现`simulated=false`事件，重复心跳不重复建事件 | `/events` |
| 异常恢复 | 断开设备/中继后恢复 | 观察5分钟 | Backend仍健康；算法先unavailable，再自动恢复 | `/system`等 |

每次验证应记录Git hash、时间、设备脱敏ID、配置profile、输入说明、屏幕录像和结果JSON脱敏副本。通过标准不以HTTP 200或播放器ready替代真实画面确认。性能验证另用同步时钟和逐帧标记，避免把模型耗时当端到端延迟。
