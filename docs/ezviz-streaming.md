# EZVIZ Real-time Streaming (M3 / M3.1)

M3 只建立真实 H6c 的浏览器播放与 Ubuntu/ffprobe 消费链路，不包含 AI、设备控制、回放、截图或双向语音。

## 数据链路

```text
CS-H6c -> EZVIZ Platform -> temporary HLS address
                                  |          |
                                  v          v
                      official Web player   ffprobe
                                  |          |
                                  v          v
                            /monitor     media metadata
```

Backend 保持 `Route -> StreamService -> EzvizStreamAdapter -> EZVIZ Open API`。Frontend 只使用 CareShield Stream Schema，不了解 AppKey、AppSecret、AccessToken 或萤石原始响应。

## 官方接口与协议选择

实时地址使用萤石官方接口：

```text
POST https://open.ys7.com/api/lapp/v2/live/address/get
```

M3.1 固定请求实时预览（`type=1`）、HLS（`protocol=2`）、主码流（`quality=1`）、H.265 能力（`supportH265=1`）、TS 封装（`containerFormat=0`）、音频不静音（`mute=0`）和 3600 秒有效期。官方兼容性表仅列出 H.265 直播的 TS 封装，因此不选择 fMP4。官方接口允许的有效期范围更大，但一小时足以覆盖当前实时会话，也降低地址泄露后的暴露窗口。

HLS 同时适合浏览器和 ffprobe。现代浏览器不原生支持 RTMP；M3 不为协议数量引入 RTMP/HTTP-FLV 转封装。浏览器播放器使用萤石官方 `@ezuikit/player-hls` 2.0.0，并明确选择 WASM/WebGL `soft` 解码；`isEzviz=true` 让官方播放器附加 H.264/H.265 客户端能力标记。当前真实设备的标准 HLS manifest 是短 `ENDLIST` 片段，而官方兼容性表未列出 H.265 的 `ended` 事件。页面因此监测媒体时间推进；停帧超过阈值后通过 Backend 重新取得临时地址并重建播放器，不依赖缺失的事件，也不在前端长期保存地址。

官方资料：

- [获取设备实时流地址](https://open.ys7.com/help/1414)
- [直播协议介绍](https://open.ys7.com/help/1752)
- [HLS 播放器简介](https://open.ys7.com/help/3704)
- [HLS 播放器安装](https://open.ys7.com/help/3712)
- [HLS 播放器兼容性](https://open.ys7.com/help/3715)
- [HLS 播放器事件](https://open.ys7.com/help/3716)
- [播放器下载与版本](https://open.ys7.com/cn/s/download)

## M3.1 误判修复

旧实现没有发送 `supportH265` 和 `containerFormat`，并设置了 `isEzviz=false`。它还把播放器首帧或时间推进直接当作 `LIVE`。萤石错误提示本身也是一段有效 H.264 视频，因此会同时满足 HTTP 成功、ffprobe 成功和播放器时间推进，造成错误验收。

M3.1 做了两层修正：

- 取流端显式请求 H.265 + TS，并保留音频；浏览器强制使用官方 H.265 软件解码链。
- 诊断端区分 `probe_success` 与 `camera_content_verified`。ffprobe 只证明媒体可读取，不能证明画面来自摄像机；播放器解码后先显示 `Verification required`，只有人工确认当前画面后才显示 `LIVE`。

不要把 `512×288 / 5 FPS` 写成自动拒绝规则；它只是本次错误提示视频的观测特征，不足以普遍判定媒体内容。

本次对真实 H6c 的临时 HLS 地址进行安全探测并查看临时帧，得到：

- Video：HEVC/H.265 Main，1920×1080，约 15 FPS，yuv420p
- Audio：AAC LC，16000 Hz，mono
- Video/Audio bitrate：当前 manifest/ffprobe 未提供

临时帧仅保存在 `/tmp` 验收，不进入仓库；完整设备序列号、播放地址、Token 和 Secret 均未写入文档。

## 安全边界

- AppKey/AppSecret 仅位于被 Git 忽略的根目录 `.env`，由 Backend 读取。
- AccessToken 仅在 Backend 内存中缓存，不返回浏览器。
- HLS 地址不写入 `.env`、数据库、README、日志或测试 fixture。
- `/stream` 只为当前播放器会话返回临时地址；`/media-info` 不返回地址。
- 异常只返回安全摘要和必要的萤石错误码，不回显第三方原始响应。
- UI 不显示完整设备序列号。

## Web 播放

Frontend 构建前由 `npm run prepare:hls` 将官方包内的 `decoder.wasm` 与 `decoder.worker.js` 复制到被 Git 忽略的 `public/ezuikit-hls/`。这些是 npm 安装产物，不在仓库中重复保存。

访问：

```text
http://localhost:5173/monitor
```

页面会选择真实在线 H6c、请求临时地址并创建播放器。浏览器音频策略要求用户手势，因此首次连接后需点击“开始实时播放”；播放器保持静音启动，用户可再通过官方音量控件开启声音。刷新/重连会销毁旧播放器，再从 Backend 请求新地址。首帧出现只表示媒体已解码；页面会要求人工确认画面内容，确认前不会显示 `LIVE`。

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
