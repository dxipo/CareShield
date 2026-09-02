# 参赛证据清单

| 证明内容 | 当前状态 | 代码证据 | 实验/日志证据 | 页面证据 | 建议截图 | 是否可用于正式材料 |
|---|---|---|---|---|---|---|
| 萤石AppKey安全配置 | 已实现 | config/token manager | `.env` ignore检查 | 不展示 | `.env.example`+ignore，不截真实值 | 是 |
| H6c与设备在线 | 已验证历史 | device adapter/service | 实时API需复核 | `/devices` | 型号、Online、脱敏序列号 | 是，答辩前刷新 |
| 真实视频流 | 已验证历史 | stream service/player | ffprobe+人工画面 | 首页 | 摄像头动作与页面同框 | 是 |
| 真实音频 | 已验证历史 | media probe/audio reader | AAC LC/16k/mono | 播放器/诈骗页 | 音轨诊断 | 是 |
| Backend | 已完成 | FastAPI routes | pytest/health需归档 | `/system` | health与Compose healthy | 是 |
| AI Worker | 已完成 | heartbeat/runtime | current status需归档 | `/algorithms` | Worker Online/GPU | 是 |
| 人物检测 | 已完成 | YOLO person adapter | 实际preview需录屏 | 跌倒页 | 站立与横卧框 | 是 |
| Tracking | 已完成 | `tracking.py` | 多场景统计待补 | 跌倒页 | 连续ID/短遮挡录屏 | 有限 |
| Pose | 已完成 | YOLO pose/CareShield schema | 实际COCO17 preview | 跌倒页 | 骨架连线 | 是 |
| MotionCLIP | 已实现未充分验证 | motionclip-worker | 阈值配置；无外部验证 | 风险页 | 距离+8概念+解释 | 只能写研究评估 |
| KINECAL跌倒风险 | 已实现未充分验证 | kinecal worker | 74%来源待回收；高风险0/7 | 风险页 | 三类分数+review | 限制性使用 |
| 实时跌倒检测 | 已实现未充分验证 | STGCN pipeline | 88/88仅兼容性 | 跌倒页 | score、状态、告警 | 可证明运行，不证明准确率 |
| 诈骗识别 | 已实现未充分验证 | fraud-worker | 无正式准确率 | 诈骗页 | 转写、LLM used、告警 | 可证明运行，不证明准确率 |
| Redis | 已完成 | realtime store | 单元测试 | 算法/事件页 | Redis Healthy+刷新恢复 | 是 |
| WebSocket | 已完成 | realtime hub/client | M4测试 | 多页面实时变化 | Connected及状态变化 | 是 |
| Dashboard | 已完成 | DashboardView | 前端build | `/dashboard` | 总览+直播+趋势 | 是 |
| Docker | 已完成 | compose/Dockerfiles | `compose ps`需归档 | 无 | 全服务healthy | 是 |
| PostgreSQL业务 | 未实现 | 仅Compose | 无表/无查询 | 无 | 不建议截图 | 否 |
| 实验指标 | 严重不足 | 少量配置/文档 | 缺独立测试与原始输出 | 无 | 后续实验图表 | 否/待补 |

## 下一步必须补充的证据和截图

### P0 必须补

固定Git hash的全服务 `docker compose ps`、全部测试汇总、H6c在线页、真实画面人工验证录屏、跌倒检测正常/疑似/告警全流程、摄像机动作到页面告警同步计时、三类算法逐样本测试集和混淆矩阵、诈骗正常/诈骗对照、Secret扫描结果。

### P1 建议补

GPU型号/显存和模型checksum、HTTP-FLV共享中继多消费者、断网重连、风险评估完整进度及历史回看、28参数原始JSON与8项重点页、SMPL-X两种视图、Redis刷新恢复、WebSocket断线重连。

### P2 有时间再补

2小时稳定性、不同光照/遮挡/多人、不同身高和服装、ASR噪声鲁棒性、CPU降级、浏览器兼容性与1366×768布局。
