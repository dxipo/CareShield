# EZVIZ Real-time Streaming (M3 / M3.1 / M5.1)

M3/M3.1 建立真实 H6c 的标准 HLS 与媒体探测链；M5.1 将浏览器切换到低延迟 EZOPEN；M5.2 保留 HLS 给 Backend 诊断，并将 AI Worker 输入切换为 HTTP-FLV。

## 数据链路

```text
CS-H6c -> EZVIZ Platform
                |-- EZOPEN -> official ezuikit-js -> /dashboard
                |-- temporary HLS -> ffprobe -> safe media metadata
                `-- temporary HTTP-FLV -> AI Worker -> AI results
```

Backend 保持 `Route -> StreamService -> EZVIZ Adapter/TokenManager -> EZVIZ Platform`。Frontend 不接触 AppKey/AppSecret 或萤石原始响应。EZOPEN 官方 Web SDK 明确要求 AccessToken，因此专用会话只在运行时把 Token 交给播放器。

## 官方接口与协议选择

实时地址使用萤石官方接口：

```text
POST https://open.ys7.com/api/lapp/v2/live/address/get
```

M3.1 固定请求实时预览（`type=1`）、HLS（`protocol=2`）、主码流（`quality=1`）、H.265 能力（`supportH265=1`）、TS 封装（`containerFormat=0`）、音频不静音（`mute=0`）和 3600 秒有效期。官方兼容性表仅列出 H.265 直播的 TS 封装，因此不选择 fMP4。官方接口允许的有效期范围更大，但一小时足以覆盖当前实时会话，也降低地址泄露后的暴露窗口。

标准 HLS 具有约 4–10 秒的首屏与分片缓冲延迟。M5.1 浏览器改用官方推荐的 EZOPEN 私有监控协议和 `ezuikit-js` 9.0.19，官方说明其典型出流约 1 秒。播放器使用 `pcLive` 模板、v3 解码器、本地静态解码资源和 performance-priority quality；首帧事件出现后页面才显示 `LIVE`，并展示该次连接实际首帧时间。

AI Worker 不直接使用 EZOPEN：Ubuntu 上的 FFmpeg/PyAV 不支持 `ezopen://` 私有协议，萤石公开 SDK 下载列表也没有适用于通用 Ubuntu 22.04 x86_64 服务端算法的 EZOPEN SDK。M5.2 由同一个官方实时地址接口请求 `protocol=4`、`type=1`、`quality=1`、`supportH265=1`、`mute=0` 的 HTTP-FLV，且不发送仅属于 HLS 的 `containerFormat`。浏览器与算法链来自同一设备，但使用各自运行环境可稳定消费的低延迟协议。

2026-08-26 本机旧 HLS 实测：新会话首帧相对摄像机 OSD 约落后 16.2 秒；追到流尾后约落后 6.2 秒。该结果不再代表 M5.2 AI 输入。HTTP-FLV 的真实持续运行、重连和端到端延迟需要在部署新 Worker 后单独验收；推理耗时不能替代摄像机到算法的总延迟。

官方资料：

- [获取设备实时流地址](https://open.ys7.com/help/1414)
- [直播协议介绍](https://open.ys7.com/help/1752)
- [HLS 播放器简介](https://open.ys7.com/help/3704)
- [HLS 播放器安装](https://open.ys7.com/help/3712)
- [HLS 播放器兼容性](https://open.ys7.com/help/3715)
- [HLS 播放器事件](https://open.ys7.com/help/3716)
- [播放器下载与版本](https://open.ys7.com/cn/s/download)
- [EZOPEN 协议说明](https://open.ys7.com/help/1751)
- [视频直播协议对比](https://open.ys7.com/help/2821)
- [EZUIKit Web 接入](https://open.ys7.com/help/4294)

## M3.1 误判修复

旧实现没有发送 `supportH265` 和 `containerFormat`，并设置了 `isEzviz=false`。它还把播放器首帧或时间推进直接当作 `LIVE`。萤石错误提示本身也是一段有效 H.264 视频，因此会同时满足 HTTP 成功、ffprobe 成功和播放器时间推进，造成错误验收。

M3.1 做了两层修正：

- 取流端显式请求 H.265 + TS，并保留音频；浏览器强制使用官方 H.265 软件解码链。
- 诊断端区分 `probe_success` 与 `camera_content_verified`。ffprobe 只证明媒体可读取，不能证明画面来自摄像机。M3.1 的 HLS 页面曾使用人工确认门；M5.1 的 EZOPEN 页面改由官方 SDK 首帧事件驱动 `LIVE`，真实画面仍需在正式验收时人工查看。

不要把 `512×288 / 5 FPS` 写成自动拒绝规则；它只是本次错误提示视频的观测特征，不足以普遍判定媒体内容。

本次对真实 H6c 的临时 HLS 地址进行安全探测并查看临时帧，得到：

- Video：HEVC/H.265 Main，1920×1080，约 15 FPS，yuv420p
- Audio：AAC LC，16000 Hz，mono
- Video/Audio bitrate：当前 manifest/ffprobe 未提供

临时帧仅保存在 `/tmp` 验收，不进入仓库；完整设备序列号、播放地址、Token 和 Secret 均未写入文档。

## 安全边界

- AppKey/AppSecret 仅位于被 Git 忽略的根目录 `.env`，由 Backend 读取。
- AccessToken 默认只在 Backend 内存中缓存。启用 EZOPEN Web 后，仅专用播放会话在运行时返回给官方 SDK，响应强制 `Cache-Control: no-store, private` 和 `Pragma: no-cache`。
- HLS/HTTP-FLV 地址不写入 `.env`、数据库、README、日志或测试 fixture。
- `/browser-playback` 仅用于可信浏览器会话；Token 和 EZOPEN URL 不写日志或持久化。
- `/stream` 保留给诊断和内部媒体链；`/media-info` 不返回任何播放地址。
- 异常只返回安全摘要和必要的萤石错误码，不回显第三方原始响应。
- UI 不显示完整设备序列号。

## Web 播放

Frontend 构建前由 `npm run prepare:player` 将官方包内 `ezuikit_static` 复制到被 Git 忽略的 `public/ezuikit_static/`。这些是 npm 安装产物，不在仓库中重复保存。

访问：

```text
http://localhost:5173/dashboard
```

页面会选择真实在线 H6c、请求禁止缓存的 EZOPEN 会话并创建播放器。刷新/重连会销毁旧实例并获取新会话。首帧事件触发 `LIVE`，不再显示遮挡播放器控制栏的人工确认按钮。浏览器阻止自动播放声音时，用户通过官方音量控件开启声音。

## ffprobe

Backend Docker 镜像只为 M3 媒体诊断安装 Debian 的 `ffmpeg` 包并调用其中的 `ffprobe`。它不引入 CUDA、PyTorch 或 AI 依赖。未来连续媒体消费应移入独立 AI Worker；当前 Backend 探测是低频诊断端点，不是推理管线。

本机诊断：

```bash
python3 scripts/probe_ezviz_stream.py
```

脚本从 `/api/devices` 选择在线 H6c，再从 `/stream` 临时获取地址。标准输出只包含实际视频与音频元数据。失败信息不会包含播放地址或凭据。

## 常见错误

- `503 EZVIZ integration is not configured`：检查本机 `.env` 后重启 Backend。
- `503 EZVIZ device is offline`：确认设备供电与网络状态。
- `502 ... code 60019`：设备视频加密阻止标准地址播放；不要在代码中硬编码验证码。
- `Unable to inspect the live stream`：可能是地址过期、网络超时或媒体格式暂时不可读，重新请求地址后再探测。

实际 codec、分辨率、FPS 与音频能力必须以当前设备的实时 ffprobe 结果为准，不依据产品宣传参数推断。
