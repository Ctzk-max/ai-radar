# 发布与恢复

生产为 `ai-radar.go.altare.global`。保留旧应用、现有域名、旧 KV 及旧部署记录。推送部署为 **Ask me first**。

旧生产提交 `40ca6eb82fbb3b1be66bd9182bb5d3526bf6eb37`。旧运行配置为 Node.js 26，根目录仓库，安装 `npm install`，启动 `node bootstrap-fix.cjs`。旧变量有 `ADMIN_PASSWORD`、`KV_URL`、`KV_NAMESPACE`、`KV_TOKEN`。旧站点在本次接手前已停止，恢复旧状态仍可能出现历史 KV 401。

新生产使用 Altare 的 Python 3.13 及托管 PostgreSQL 17。Altare 文档列出 Always Free 的数据库配额为 256 MB RAM 和 1 GB 磁盘，夜间备份保留三天。控制台的“连接到应用”操作会注入变量并触发部署，发布窗口内统一处理。上线验证前记录回滚提交及变量键名，保留实际秘密在控制台。

[Altare 部署](https://docs.altare.gg/apps) · [PostgreSQL 配额、TLS 与备份](https://docs.altare.gg/databases/postgres)
