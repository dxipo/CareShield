# EZVIZ 临时语音播报

## 当前实现

CareShield Backend 已实现萤石临时语音播报的最小安全链路：

```text
authenticated internal caller
  -> /internal/media/devices/{device_serial}/voice
  -> VoiceBroadcastService
  -> EzvizClient
  -> POST /api/lapp/voice/sendonce
  -> H6c speaker
```

浏览器和 AI Worker 都不会获得 EZVIZ AppSecret 或 AccessToken。音频仅在请求内存中短暂存在，不写入数据库、Redis、日志或 Git。内部接口继续使用 `AI_WORKER_SHARED_TOKEN` 鉴权。

## 诈骗风险告警预留

Fraud Worker 已接入上述内部接口，但默认通过
`FRAUD_VOICE_ALERT_ENABLED=false` 关闭。当真实诈骗检测结果首次进入
`warning` 或 `critical` 告警生命周期时，Worker 最多下发一次由运维人员
挂载的 WAV/MP3/AAC 提示音；持续告警不会重复下发，恢复后仍受默认 300 秒
冷却时间约束。语音失败不会中断诈骗结果写入 Backend、Redis 或 WebSocket。

启用前需同时满足：萤石云广播资源包有效、设备能力支持、提示音以只读方式
放入本地 `fraud-worker/assets/`（该目录中的音频被 Git 忽略，并只读挂载到
容器 `/alerts`），然后设置：

```env
FRAUD_VOICE_ALERT_ENABLED=true
FRAUD_VOICE_ALERT_AUDIO_PATH=/alerts/fraud-warning.aac
FRAUD_VOICE_ALERT_CHANNEL_NO=1
FRAUD_VOICE_ALERT_COOLDOWN_SECONDS=300
```

当前资金条件下保持关闭，未执行新的收费播报请求，也未将该能力标记为实机
出声通过。

## 官方能力与约束

- 设备能力通过 `POST /api/lapp/device/capacity` 查询。
- 临时播报要求 `support_talk=1` 或 `support_talk=3`。
- `POST /api/lapp/voice/sendonce` 接受 WAV、MP3、AAC，最长 60 秒。
- API 页面标注上限 20 MB，产品操作指南标注上限 5 MB；CareShield 采用更严格的 5 MB。
- 产品操作指南要求设备支持 AAC。正式告警音频建议预编码为 AAC、单声道。
- 云广播是付费服务，必须存在有效资源包；错误码 `111000` 表示资源包余量不足。

## 真实验证记录（2026-09-02）

- 真实设备：`CS-H6c-V200-8H8WFL`（序列号未记录）
- 设备在线：是
- `support_talk`：`1`
- `support_alarm_voice`：`1`
- 测试文件：本机 `/tmp` 中生成的约 3.8 秒 WAV，未保存进仓库
- 调用结果：萤石返回 `111000`
- 结论：设备能力和 API 请求链已验证；账号当前没有云广播资源包，因此尚未完成扬声器实际出声验证。

## 完成物理验收的步骤

1. 在萤石开放平台控制台开通云广播并购买可用资源包。
2. 确认资源包余量大于零。
3. 准备不超过 60 秒、5 MB 的 AAC 测试音频。
4. 使用内部 Worker Token 调用 CareShield 内部语音接口。
5. 现场确认 H6c 扬声器实际播放，并记录调用时间和人工确认结果。

正式接入跌倒告警前，还需要增加事件级冷却、重复播报抑制和人工确认后的停止升级策略，避免循环视频或重复检测造成连续播报。

## 官方文档

- [获取设备能力集](https://open.ys7.com/help/678)
- [临时语音下发接口](https://open.ys7.com/help/1252)
- [云广播操作指南](https://open.ys7.com/help/5116)
- [云广播产品概述](https://open.ys7.com/help/5111)
