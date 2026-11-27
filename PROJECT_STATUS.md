# AI Radar 当前状态

2026-11-27（北京时间）。保留既有 Stockholm 应用、域名、旧 KV 和 GitHub 仓库。旧应用接手前已停止，外部 HTTPS 502，原生产提交 `40ca6eb`，旧 KV 显示 0 键。远端恢复标签 `archive/pre-rebuild-2026-11-27` 和本地 `.git/ai-radar-pre-rebuild.bundle` 已核对，生产推送已改为手动确认。

新版已能在正式域名访问登录页。用户认证前的 HTTPS、匿名 API 拒绝和生产采集均实测。改用既有应用磁盘的 SQLite WAL，关闭空库初始化后成功跨部署启动。托管 PostgreSQL 显示运行，但应用和外部 DNS 均无法解析主机名。

本地已有 22 个自动测试通过。自动来源发现、官方模型规格和小时级调度心跳进入下一次手动部署。管理员有状态线上验收需用户完成一次身份验证。24 小时观测窗口正在累计。

恢复工作时检查 `git status --short --branch`、`git log -8 --oneline`、线上 `/health/` 与 [TASKS.md](TASKS.md)。证据及限制见 [TEST_REPORT.md](TEST_REPORT.md)。
