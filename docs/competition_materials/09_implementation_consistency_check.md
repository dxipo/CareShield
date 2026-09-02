# 实现一致性检查

| 议题 | 当前实际情况 | 不一致/风险 | 正式材料准确说法 |
|---|---|---|---|
| 实时跌倒模型 | STGCN-Extend，内部为ST-GCN++ backbone+预测decoder+二分类head | 不应写Uni-GCN；也不能简写成普通ST-GCN++ | “STGCN-Extend时序骨架跌倒二分类模型” |
| 跌倒风险模型 | KINECAL迁移ST-GCN++ action-adapter三分类 | README旧阶段曾让MotionCLIP承担风险主结果 | “KINECAL ST-GCN++跌倒史队列研究分级” |
| MotionCLIP | 健康参考距离+8运动概念 | 页面/旧文档“神经运动功能分析”过宽，亦不能称疾病预测 | “基于MotionCLIP的神经退行性疾病相关运动功能评估技术” |
| 人物追踪 | 自研IoU/中心距离轻量关联 | 官方文档链接含Ultralytics track，但代码未用其tracker | “轻量几何人物关联与ID保持” |
| AI媒体协议 | EZVIZ HTTP-FLV→media-relay→内部RTSP | `AGENTS.md`仍写AI Worker使用临时HLS | “浏览器EZOPEN；服务端算法共享HTTP-FLV转RTSP；HLS仅诊断” |
| 风险采集 | 共享中继短时fMP4环形录制 | 早期M6文档写独立HLS采集，后文已更新 | 以`media-relay.md`和当前compose为准 |
| 风险事件 | Redis有界列表+24h latch | README早期说不是Event Center，当前页面已有事件 | “已实现实时风险事件展示，未实现正式数据库档案和处置闭环” |
| PostgreSQL | 容器健康，业务未使用 | 架构图易误画为已存业务 | 标“基础设施预留/尚未建立业务表” |
| 模拟数据 | 仅pipeline_test明确simulated=true和测试fixture | 算法管理会显示测试结果 | 正式业务页只消费simulated=false |
| 风险概率 | STGCN softmax未校准；KINECAL类别置信度；MotionCLIP距离；诈骗heuristic score | 页面“score/概率”易被误读 | 分别写“未校准softmax分数/分类置信度/参考距离/证据强度” |
| 直播真实性 | firstFrame仅证明解码，人工移动确认真实内容 | 曾把萤石错误提示视频误判成功 | “协议可解码+人工画面确认”双门槛 |
| M7状态 | README称进行中，代码/页面已接入 | 缺正式精度与长期验证 | “工程基线已接入，算法有效性待补测” |
| Git版本 | 当前分支有大量未提交实现，远端停在`bcf5d2b` | 本机实现不等于可交付版本 | 文档附当前commit+dirty状态，发布前正式提交/打tag |

## 重点修订建议

第一，后续所有参赛文档使用三种严格名称：实时“STGCN-Extend跌倒二分类”、风险“KINECAL ST-GCN++队列分级”、运动功能“基于MotionCLIP的神经退行性疾病相关运动功能评估技术”。第二，架构图不得把 PostgreSQL 连到当前业务结果，Redis才是实际状态和事件存储。第三，不把模型文件存在、单元测试或页面出现结果等同于准确率。第四，正式交付前应把当前工作区整理为可追溯commit，并同步README、AGENTS和版本号。
