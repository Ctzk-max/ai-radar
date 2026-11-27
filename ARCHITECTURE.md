# AI Radar 架构

应用使用 Python 3.13、Django 5.2 LTS、Waitress 和服务端 HTML。Altare 既有容器只提供 Node.js 和静态选项，因此 Node 下载校验后的运行时并启动 Python。应用进程内运行独立调度线程，最多四路并行采集。

生产使用既有应用磁盘上的 SQLite WAL。数据库路径显式配置，缺少已初始化文件时启动失败。PostgreSQL 后端保留，Altare 新建托管库的标准主机名当前 NXDOMAIN，切换需要重新验证可达性及迁移。

- 来源模型保存适配器、频率、健康、退避和网络缓存元数据。采集租约和来源版本避免重叠及旧配置结果写回。
- 事件保存时间、摘要、福利证据及个人状态，归一化 URL 和同主题近似标题合并事件。不同模型版本分别保留。
- 安全 HTTP 客户端逐跳验证目标和 DNS，将连接固定到校验后的公开地址，按原域名验证 TLS，限制响应、超时及跳转。
- 核验需要匹配官方平台和域名，并能提取相关福利措辞。日期、资格、续费和地区缺失时保留空值或引用原文。增量发现从近期相关内容提取公开链接，每日最多试抓四个，结果进入待确认来源。
- 模型记录区分独立测试、厂商规格、社区体验，保存版本、指标、单位、方法、时间及链接。每小时调度心跳和采集日志持久化，外部 HTTPS 健康检查由 Altare 监测。
- PBKDF2、服务端会话、Secure、HttpOnly、SameSite=Strict、CSRF 及 CSP 保护私有页面。Cloudflare 边缘连接通过 TCP 对端地址核验，裸节点拒绝 POST。日志记录结构化错误和计数。
- 设置可导出配置、收藏和 JSON 数据。恢复使用事务。生产 SQLite 每日生成数据库快照并做完整性检查，本地保留七份。

[Django 5.2 LTS](https://docs.djangoproject.com/en/5.2/releases/5.2/) · [Altare Apps](https://docs.altare.gg/apps) · [Altare Postgres](https://docs.altare.gg/databases/postgres) · [Cloudflare 代理网段](https://www.cloudflare.com/ips/)
