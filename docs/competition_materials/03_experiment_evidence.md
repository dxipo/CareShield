# 实验与实测证据底稿

## 1. 可追溯结果

| 项目 | 已有证据 | 可得结论 | 正式材料限制 |
|---|---|---|---|
| H6c 媒体 | ffprobe/人工验收记录：HEVC Main、1920×1080、约15 FPS、yuv420p；AAC LC、16 kHz、mono | 媒体链可承载真实视频和音频 | bitrate 未取得；应补保存脱敏原始命令输出 |
| EZOPEN | 页面真实画面、首帧事件；此前用户观察几乎无延迟 | 浏览器低延迟直播可用 | 无统一时钟测量，不能写精确端到端延迟 |
| HLS | 旧会话观察：首屏约16.2 s，追到流尾约6.2 s | 不适合作为当前实时算法链 | 单次环境观测，非统计结果 |
| STGCN checkpoint兼容性 | 保存的 88 样本 split 重现 88/88：34 fall、54 non-fall | 架构、预处理和权重兼容 | 非独立跨受试者验证，不得称部署准确率100% |
| STGCN 数据 | 440 clips：200 fall、240 non-fall | 可说明 checkpoint 的研究数据构成 | 主体数量、划分独立性不足 |
| VisionMD smoke test | 5秒、30 FPS全身样例得到16个HS/TO、28/28参数 | 处理链能产出事件和参数 | 单一样例，不代表参数准确性 |
| GVHMR真实片段 | 5秒真实H6c片段→150帧；两类视频1280×720@30；21×3世界骨架全有限 | 几何恢复、参数导出和渲染链通过 | 不代表风险模型有效性或网格精度 |
| MotionCLIP阈值选择 | 141 walks、83 subjects、macro-F1 0.505334（训练集阈值选择文件） | 可追溯阈值来源 | 不是外部验证，不宜作为系统性能 |
| KINECAL | 文档记录单一3m walk held-out accuracy 74%；高风险 recall 0/7 | 暴露当前敏感性局限 | 原始评估JSON未在仓库，正式引用前需回收训练输出 |

## 2. 跌倒风险算法对比实验

【当前仓库未发现可靠、完整的正式对比实验，不能作为正式实验结果】。仓库没有同时包含数据划分、逐样本预测、混淆矩阵和可复算脚本。KINECAL 的 74% 与高风险 0/7 仅出现在说明文档；MotionCLIP 的 0.505334 是阈值选择 macro-F1，不是与基线模型的独立测试。

最小补测方案：冻结 subject-level train/validation/test 划分；至少比较 KINECAL ST-GCN++、去除 action adapter、仅步态参数分类器三项；保存逐样本 ID 哈希、真实标签、预测类别和三类分数；报告 accuracy、macro precision/recall/F1、balanced accuracy、one-vs-rest AUC及95% bootstrap CI；分别报告 NF/FHs/FHm 混淆矩阵，并单独测试真实 H6c/GVHMR 域。

## 3. 跌倒检测性能

【当前仓库未发现可靠实测 TP、FP、TN、FN、Precision、Recall、F1、误报率、漏报率、持续运行时长或端到端告警时间】。实时代码会产生 FPS 与推理耗时 runtime metadata，但这是瞬时运行遥测，仓库未保存版本化测试结果。88/88 只证明旧 split 兼容。

最小补测方案：采用明确授权的非老人安全演示集，按受试者隔离，覆盖跌倒、坐下、弯腰、下蹲、躺床、遮挡和多人；将事件级判定窗口定义为动作前3秒至倒地后5秒；保存事件级 TP/FP/FN、非事件时长和首次告警时间；报告事件 recall、precision、F1、每小时误报、漏报、AI FPS、P50/P95推理耗时、摄像机动作到页面告警P50/P95及2小时稳定性。

## 4. 诈骗识别准确率

【待补测】。当前只有规则、ASR配置、端点切分、LLM JSON和隐私逻辑的单元测试；没有标注正常/诈骗语料、样本数和逐类混淆矩阵。正式材料不能给出 Accuracy、Precision、Recall 或 F1。

最小补测方案：建立授权中文对话集，按说话人隔离；覆盖验证码、转账、公检法、亲属求助、投资、保健品、退款及相似正常对话。分别测试 ASR文本、规则-only、规则+Qwen；保存 WER/CER、utterance级和会话级 precision/recall/F1、每小时误报、漏报及P50/P95端到端延迟。禁止保存真实家庭敏感对话。

## 5. 功能测试资产现状

仓库包含 49 个 Backend、39 个实时 AI Worker、36 个 fall-risk-worker、5 个 MotionCLIP、3 个 KINECAL、10 个 fraud-worker、4 个 media-relay 和5个前端测试定义。这些数字表示测试代码数量，不等于当前一次完整执行通过数量；本次文档任务未改变业务代码，也未在无 Docker 权限条件下重跑全栈测试。
