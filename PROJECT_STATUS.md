# AI Radar 当前状态

2026-11-27（Asia/Shanghai）。正式生产仍为 Stockholm 的旧应用。控制台显示旧应用已停止，外部 HTTPS 返回 502，生产记录为 `40ca6eb`。生产 `main` 推送策略已由自动切换为 **Ask me first** 并复查。旧运行方式为 Node.js 26，`npm install` → `node bootstrap-fix.cjs`。旧 KV 显示 0 键，Altare Postgres 当前无数据库。现有应用资源分配为 2 GiB / 75% CPU / 10 GiB，实际团队总额为 4 GiB / 125% CPU / 40 GiB / 2 个应用槽位。

旧代码已固定到本地标签 `archive/pre-rebuild-2026-11-27` ，验证了 `.git/ai-radar-pre-rebuild.bundle` 的完整历史。新代码在 `rebuild/ai-radar`。GitHub 连接器可用且有写权限，本机 Git 尚未登录 GitHub 写入。

恢复工作时先检查 `git status --short --branch`、`git log -8 --oneline` 与 [TASKS.md](TASKS.md)。线上验收及长时观察有独立证据门槛。环境变量的记录仅包含键名。
