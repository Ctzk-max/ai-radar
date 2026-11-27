# AI Radar 测试报告

| 检查 | 2026-11-27 结果 |
|---|---|
| Django 自动测试 | 22 个通过。覆盖认证、限流、CSRF、XSS、SSRF、代理来源、收藏、领取、搜索偏好、来源 CRUD、导入、备份恢复、采集退避、租约、去重、候选和评测解析 |
| 迁移与依赖 | 迁移检查和 `pip check` 通过。生产安全检查按平台域名策略忽略 HSTS preload 通用建议 |
| 真实采集 | 32 候选中 31 可解析，29 启用。初次本地库记录 120 条情报，最近三天 19 条。真实数据导入独立评测 47 条、官方规格 32 条 |
| Chrome | 本地登录、精选及模型页通过。390 × 844 下，首页 19 张卡片单列显示，未横向溢出 |
| 本地重启与性能 | 新进程打开既有磁盘库。100 次私有 feed API 请求，6 并发，中位 36.6 ms，P95 53.9 ms，最大 62.1 ms，19 条真实数据 |
| Altare 匿名验收 | `64b40888651f` 生产健康 200、登录页 200、未登录私有 API 401，登录页面和会话响应保留 Secure、CSP 和 no-store。裸节点 GET 返回 308 |
| Altare 真实数据 | 日志显示 RSS、GitHub 及网页真实入库。SQLite 关闭空库初始化后成功跨部署启动。数据库主机从容器报告 DNS 失败，Google 和 Cloudflare DNS 都返回 NXDOMAIN |
| 管理员有状态验收 | 需核对用户登录、收藏、领取、来源 CRUD 和重启后的同一记录 |
| 24 小时 | Altare 分钟健康监控已启用。应用记录采集与心跳。尚未取得完整观察窗口 |

主要组件许可证已核对，Django BSD-3、psycopg LGPL-3、feedparser BSD-2、Beautiful Soup 与 WhiteNoise MIT、Waitress ZPL 2.1。锁定版本见 [requirements.txt](requirements.txt)。
