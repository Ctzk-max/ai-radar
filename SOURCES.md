# 信息源与核验

2026-11-27 17:49（北京时间）用实际采集适配器试抓 32 个候选，31 个返回可解析内容，29 个启用。GitHub 使用公开 Releases Atom。

| 来源 | 适配器 | 一轮解析 | 最新条目（UTC）或验证结果 |
|---|---|---:|---|
| [OpenAI News](https://openai.com/news/rss.xml) | rss | 65 | 2026-11-24 |
| [OpenAI API Changelog](https://developers.openai.com/api/docs/changelog) | web | 1 | 内容或条款快照 |
| [Claude API Release Notes](https://platform.claude.com/docs/en/release-notes/overview) | web | 1 | 内容或条款快照 |
| [Google DeepMind](https://deepmind.google/blog/rss.xml) | rss | 65 | 2026-11-24 |
| [Google Gemini Blog](https://blog.google/products/gemini/rss/) | rss | 20 | 2026-11-24 |
| [DeepSeek API 更新日志](https://api-docs.deepseek.com/zh-cn/updates/) | web | 23 | 2026-11-13 |
| [Qwen 官方模型](https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1&limit=25) | web | 25 | 2026-10-09 |
| [Qwen Blog（历史）](https://qwenlm.github.io/blog/index.xml) | rss | 44 | 停用，近期更新不足 |
| [Z.ai 开发者更新](https://docs.z.ai/release-notes/new-released) | web | 1 | 内容或条款快照 |
| [xAI API Release Notes](https://docs.x.ai/developers/release-notes) | web | 1 | 内容或条款快照 |
| [OpenAI Codex Releases](https://github.com/openai/codex) | github | 10 | 2026-11-26 |
| [OpenCode Releases](https://github.com/anomalyco/opencode) | github | 10 | 2026-11-26 |
| [Claude Code Releases](https://github.com/anthropics/claude-code) | github | 10 | 2026-11-25 |
| [Hugging Face Blog](https://huggingface.co/blog/feed.xml) | rss | 65 | 2026-11-26 |
| [Simon Willison](https://simonwillison.net/atom/everything/) | rss | 30 | 2026-11-26 |
| [Latent Space](https://www.latent.space/feed) | rss | 20 | 2026-11-26 |
| [One Useful Thing · Ethan Mollick](https://www.oneusefulthing.org/feed) | rss | 20 | 2026-11-09 |
| [SWE-bench Releases](https://github.com/SWE-bench/SWE-bench) | github | 10 | 2026-08-18 |
| [Artificial Analysis · 方法](https://artificialanalysis.ai/methodology) | web | 1 | 内容或条款快照 |
| [GitHub Changelog](https://github.blog/changelog/feed/) | rss | 10 | 2026-11-25 |
| [GitHub Student Developer Pack](https://education.github.com/pack) | web | 1 | 内容或条款快照 |
| [Gemini API 免费额度](https://aistudio.google.com/docs/pricing.md) | web | 1 | 内容或条款快照 |
| [Gemini API Changelog](https://aistudio.google.com/docs/changelog.md) | web | 1 | 内容或条款快照 |
| [Cursor for Students](https://cursor.com/students) | web | 1 | 内容或条款快照 |
| [OpenRouter Free Models](https://openrouter.ai/docs/guides/routing/model-variants/free) | web | 0 | 停用，TLS 校验失败 |
| [Cloudflare Workers AI Changelog](https://developers.cloudflare.com/changelog/rss/workers-ai.xml) | rss | 44 | 2026-11-12 |
| [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features) | web | 1 | 内容或条款快照 |
| [Oracle Cloud Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm) | web | 1 | 内容或条款快照 |
| [Altare Plans](https://docs.altare.gg/platform/plans) | web | 1 | 内容或条款快照 |
| [Free for Developers](https://github.com/ripienaar/free-for-dev) | web | 1 | 内容或条款快照 |
| [Hacker News · AI / 免费线索](https://hnrss.org/newest?q=AI+free&points=15) | rss | 16 | 停用，首抓 HTTP 502 后恢复，相关性有限 |
| [AI Free · 条款变更](https://aifree.dev/changes?hub=student-ai-deals) | web | 1 | 内容或条款快照 |

## 评测和 X

- SWE-bench Verified Bash Only 从维护方 JSON 导入，保存日期、试验来源与 harness 版本。Claude 和 DeepSeek API 指标来自厂商文档。[SWE-bench 数据](https://github.com/SWE-bench/swe-bench.github.io/blob/master/data/leaderboards.json) · [Claude 指标](https://platform.claude.com/docs/en/models/overview) · [DeepSeek 指标](https://api-docs.deepseek.com/quick_start/pricing/)
- Simon Willison、Ethan Mollick 和 Latent Space 的公开订阅补充 X 线索。X 官方按量计费，X 账号直连显示不支持，可配置获授权的公开 RSS 镜像。[X API 定价](https://docs.x.com/x-api/getting-started/pricing) · [X 开发者政策](https://docs.x.com/developer-terms/policy)
- 从已采集近期主题条目提取新候选。每日最多检查四个，近 120 天有两条相关带日期记录的 RSS 或 GitHub 来源进入来源管理待确认区。
