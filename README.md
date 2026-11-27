# AI Radar

私人 AI 情报站。自动关注 AI 福利、模型动态和免费云资源。首页默认显示最近三天，可搜索、收藏、追踪领取并管理公开信息源。

## 本地运行

Python 3.13 为正式部署版本。Windows 本地也可用 Python 3.11。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$radarLogin = Read-Host '设置本地测试密码' -MaskInput
$env:ADMIN_PASSWORD = $radarLogin
.\.venv\Scripts\python serve.py
```

打开 `http://127.0.0.1:8018`。本地默认 SQLite。Windows 网络若返回 198.18.0.0/15 合成地址，可临时设置 `RADAR_LOCAL_DOH=1` 对照验证。生产使用当地 DNS 及托管 PostgreSQL。应用内时间按北京时间显示。

```powershell
.\.venv\Scripts\python manage.py test
.\.venv\Scripts\python scripts\probe_sources.py .local\source-probe.json
```

[部署与恢复](DEPLOYMENT.md) · [验收矩阵](TASKS.md) · [信息来源](SOURCES.md) · [测试报告](TEST_REPORT.md)
