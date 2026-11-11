# wb-proxy

WorkBuddy / CodeBuddy 多账号反代网关：把账号池包装成 OpenAI 兼容 API，并提供中文用量看板。

本仓库是 [ardeyouxipianyi/workbuddy2api-hub](https://github.com/ardeyouxipianyi/workbuddy2api-hub) 的下游分支，详见 [UPSTREAM.md](UPSTREAM.md)。许可证为 MIT，见 [LICENSE](LICENSE)。

## 运行

纯 Python 标准库实现，无第三方运行时依赖（镜像内只额外安装 `packaging` 与 `tzdata`）。

```bash
python3 wb_proxy.py                       # 默认绑定 127.0.0.1:8788
RC_PORT=8788 python3 wb_proxy.py --host 0.0.0.0 --lan
```

生产部署用 Docker：

```bash
docker build -t wb-proxy .
docker run -d --name wb-proxy -p 127.0.0.1:8788:8788 \
  -v /path/to/accounts:/app/accounts \
  -v /path/to/usage:/app/usage \
  wb-proxy
```

> 建议端口只发布到回环地址，再用带 TLS 的反向代理对外，管理面板不应直接暴露公网。
> 管理面板只做单口令认证（PBKDF2 加盐哈希 + 每 IP 5 次/分限流），无用户名、无二次验证。

## 配置与数据

| 路径 | 内容 |
|---|---|
| `accounts/*.json` | 账号凭据（含 accessToken / refreshToken），**敏感** |
| `accounts/settings.json` | 面板口令哈希、网关 API Key、调度与限额设置，**敏感** |
| `accounts/active_realm.json` | 当前出站版本（intl / cn） |
| `usage/` | 用量事件与价格时间线 |

`accounts/` 与 `usage/` 已在 `.gitignore` **和** `.dockerignore` 中排除。部署时务必确认这两个目录的权限（建议 `700`，文件 `600`），且不要把备份放到任何站点可访问目录。

## 上游与合规

- 本项目通过非官方客户端方式访问 WorkBuddy / CodeBuddy 服务。**上游会识别并拦截非官方客户端**，由此产生的风控、限流或封禁由使用者自行承担。
- 使用他人账号凭据前，须取得账号所有人的明确授权。
- 请自行确认你的使用方式符合上游服务条款与你所在地区的法律要求。

## 结构

| 文件 | 职责 |
|---|---|
| `wb_proxy.py` | HTTP 服务、协议转换（OpenAI / Responses / Anthropic）、账号调度、管理面板后端 |
| `wb_accounts.py` | 账号对象、凭据读写、token 刷新、桌面端加密信封解密 |
| `wb_upstream_pool.py` | 账号池与就绪判定 |
| `wb_identity.py` / `wb_egress.py` | 出站身份与出口绑定 |
| `wb_pricing.py` / `wb_catalog.py` | 价格估算与模型目录 |
| `wb_settings.py` / `wb_tasks.py` / `wb_activity.py` | 面板设置、任务与活跃上报 |
| `wb_agents.py` / `wb_webtools.py` | 智能体一键配置与网页工具 |
| `dashboard.html` | 单文件管理面板 |