# AI Radar 部署与恢复

## 正式环境

- Stockholm 现有应用和域名 `https://ai-radar.go.altare.global`。
- 旧容器保持 Node.js 26。安装命令 `node scripts/altare-runtime.mjs prepare`，启动 `node scripts/altare-runtime.mjs`。启动器校验 uv SHA-256，安装 Python 3.13 与固定版本依赖。
- Push 策略保持 **Ask me first**。健康路径为 `/health/`，Altare 每分钟监控开关已启用。发布后检验健康版本 SHA 和私有采集状态。
- `RADAR_SQLITE_PATH=/home/container/.ai-radar-data/radar.sqlite3`，`RADAR_SQLITE_INIT=0`。首次建立库时曾设为 1。已有数据库丢失时应先从备份恢复。
- `RADAR_ORIGIN_HOST=se-sto07.tryaltare.ai` 是平台日志中的精确主机。跨节点迁移时复查主机及源地址。
- 生产使用已有 `ADMIN_PASSWORD`。可用 `RADAR_ADMIN_PASSWORD_HASH` 优先指定 Django 哈希。独立签名密钥保存在 Altare 的 `RADAR_SECRET_KEY`。
- 托管 PostgreSQL 已创建并注入 `DATABASE_URL` 和 `PG*`，目前主机名解析失败。数据库保留。恢复可用后优先配置厂商证书和 `verify-full`，在副本验证恢复并确认迁移后切换。
- 2026-11-28 核实生产容器的命令任务可通过实际 uv 管理的 CPython 二进制运行。部署切换后全局链接可能指向构建暂存目录，应从 `/home/container/.altare-runtime/python/` 核对实际版本目录。生产验收任务已停用，运行历史保留。

## 备份、升级与回滚

1. 在设置下载完整 JSON 备份，保留于应用盘之外。应用盘同时每日保存 SQLite 一致性快照，保留七份。
2. 空目标库迁移后执行 `python manage.py radar_backup restore 文件`。Web 恢复需要输入 `RESTORE` 才以事务替换数据。大文件可从命令行恢复。
3. 变更前记录当前版本、数据库路径和运行参数。部署后检查旧资料、领取记录、来源状态及新记录，并复核 HTTPS 边缘。
4. 通过 Altare 部署历史回滚应用。旧标签 `archive/pre-rebuild-2026-11-27` 对应 `40ca6eb82fbb3b1be66bd9182bb5d3526bf6eb37`。如需还原到旧启动器，恢复 Node.js 26、`npm install` 和 `node bootstrap-fix.cjs`。原站点接手前已停止并返回 502，原有 KV 不动。

[Altare 部署](https://docs.altare.gg/apps) · [PostgreSQL TLS 与备份](https://docs.altare.gg/databases/postgres) · [uv 发行包](https://github.com/astral-sh/uv/releases/tag/0.13.10)
