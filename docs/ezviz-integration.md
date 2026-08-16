# EZVIZ Device Integration

M2 仅接入萤石开放平台身份认证、设备列表和单设备信息，不包含视频、音频、PTZ、截图、回放或设备控制。

## 模块边界

```text
FastAPI Route
  -> DeviceService（CareShield 设备标准化）
    -> EzvizClient / EzvizTokenManager（供应商 Adapter）
      -> EZVIZ Open API
```

- `backend/app/api/` 负责 HTTP 输入输出和状态码转换。
- `backend/app/services/device_service.py` 负责映射 CareShield Device Schema。
- `backend/app/adapters/ezviz/` 负责表单请求、分页、Token 缓存和萤石错误处理。
- Frontend 只调用 CareShield API，不持有 AppKey、AppSecret 或 AccessToken。

## 官方接口依据

- [获取 AccessToken](https://open.ys7.com/help/81)
- [分页查询设备列表](https://open.ys7.com/help/673)
- [获取单个设备信息](https://open.ys7.com/help/672)

请求均为 `application/x-www-form-urlencoded` 的 POST。Token 的 `expireTime` 是毫秒级时间戳；进程内缓存会在过期前五分钟刷新，业务接口返回 `10002` 时会失效旧缓存并重试一次。

## 安全配置

复制 `.env.example` 为 `.env`，只在 `.env` 中替换 EZVIZ 示例值。`.env` 已由 `.gitignore` 排除。不要把真实凭据作为命令行参数、测试 fixture、日志内容或问题截图提交。

```bash
docker compose up -d --build
curl http://localhost:8000/api/integrations/ezviz/status
curl http://localhost:8000/api/devices
```

状态接口只返回非敏感结果。如果未配置，Backend 和 `/api/health` 仍正常工作；设备接口返回 HTTP 503。如果萤石 API 不可达或返回业务错误，设备接口返回安全的 HTTP 502 摘要，不透传完整上游响应。

## 测试

```bash
python -m pytest backend/tests
```

单元测试通过 HTTPX Mock Transport 模拟萤石 HTTP 响应，不访问真实网络，也不保存真实设备信息。
