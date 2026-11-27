# 架构

Python 与 Django 5.2 LTS 模块化单体。Django 提供服务端模板、表单、安全会话、CSRF、ORM 与迁移。Waitress 提供单进程 HTTP 服务，定时采集使用同进程低并发线程，采集租约、重试时间与运行记录持久化到数据库。生产用 Altare 托管 PostgreSQL 17，本地默认 SQLite。来源访问通过单独的安全 HTTP 客户端，HTML 仅用于提取数据，用户界面交给 Django 模板转义。

来源、事件及事件证据分别持久化。事件保存原文时间和发现时间，福利条款保留证据及空值。模型观察记录保存模型及版本、指标、值、单位、测试方法、来源类型、来源 URL 和观察时间。

生产遵循原域名、已安装的 GitHub 绑定、手动发布和保留历史部署。数据库使用独立 schema 保护可迁移的历史。凭证走 Altare 环境变量。

[Django 5.2 LTS](https://docs.djangoproject.com/en/5.2/releases/5.2/) · [Altare Apps](https://docs.altare.gg/apps) · [Altare Postgres](https://docs.altare.gg/databases/postgres)
