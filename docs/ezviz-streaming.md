# EZVIZ Real-time Streaming (M3)

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

M3 固定请求实时预览（`type=1`）、HLS（`protocol=2`）、主码流（`quality=1`）、音频不静音（`mute=0`）和 3600 秒有效期。官方接口允许的有效期范围更大，但一小时足以覆盖当前实时会话，也降低地址泄露后的暴露窗口。

HLS 同时适合浏览器和 ffprobe。现代浏览器不原生支持 RTMP；M3 不为协议数量引入 RTMP/HTTP-FLV 转封装。浏览器播放器使用萤石官方 `@ezuikit/player-hls` 2.0.0，其 `auto` 解码模式优先使用 HLS.js/MSE，浏览器无法解码时可切换 WASM 软解。当前真实设备的标准 HLS manifest 是会更新的短 `ENDLIST` 片段，因此播放器在 `ended` 后依据 SDK 的 live 模式重新加载同一临时地址；地址失效或网络失败时再由用户重连获取新地址。

官方资料：

- [获取设备实时流地址](https://open.ys7.com/help/1414)
- [直播协议介绍](https://open.ys7.com/help/1752)
- [HLS 播放器简介](https://open.ys7.com/help/3704)
- [HLS 播放器安装](https://open.ys7.com/help/3712)
- [播放器下载与版本](https://open.ys7.com/cn/s/download)

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

页面会选择真实在线 H6c、请求临时地址并创建播放器。刷新/重连会销毁旧播放器，再从 Backend 请求新地址。

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
