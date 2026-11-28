from .models import Category as C, Source as S


def entry(name, url, kind, trust, category="", platform="", weight=65, interval=180, keywords="", selector="", page_title="", enabled=True, error=""):
    return dict(name=name, url=url, kind=kind, trust=trust, category=category, platform=platform,
                weight=weight, interval=interval, keywords=keywords, selector=selector, page_title=page_title, enabled=enabled, error=error)


O, I, U = S.Trust.OFFICIAL, S.Trust.INDEPENDENT, S.Trust.COMMUNITY
R, G, W, A = S.Kind.RSS, S.Kind.GITHUB, S.Kind.WEB, S.Kind.AUTO
SOURCES = [
    entry("OpenAI News", "https://openai.com/news/rss.xml", R, O, "", "OpenAI", 75, 75),
    entry("OpenAI API Changelog", "https://developers.openai.com/api/docs/changelog", W, O, C.MODEL, "OpenAI", 80, 240, "model,free tier", "main", "OpenAI API 更新日志"),
    entry("Claude API Release Notes", "https://platform.claude.com/docs/en/release-notes/overview", W, O, C.MODEL, "Anthropic", 80, 240, "Claude,token", "main", "Claude API 更新日志"),
    entry("Google DeepMind", "https://deepmind.google/blog/rss.xml", R, O, "", "Google", 70, 120),
    entry("Google Gemini Blog", "https://blog.google/products/gemini/rss/", R, O, "", "Google", 75, 120),
    entry("DeepSeek API 更新日志", "https://api-docs.deepseek.com/zh-cn/updates/", W, O, C.MODEL, "DeepSeek", 78, 240),
    entry("Qwen 官方模型", "https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1&limit=25", W, O, C.MODEL, "Qwen", 80, 120),
    entry("Qwen Blog（历史）", "https://qwenlm.github.io/blog/index.xml", R, O, "", "Qwen", 80, 120, enabled=False),
    entry("Z.ai 开发者更新", "https://docs.z.ai/release-notes/new-released", W, O, C.MODEL, "Z.ai", 74, 240, "GLM,free", "main", "GLM 更新日志"),
    entry("xAI API Release Notes", "https://docs.x.ai/developers/release-notes", W, O, C.MODEL, "xAI", 72, 240, "Grok,free", "main", "Grok API 更新日志"),
    entry("OpenAI Codex Releases", "https://github.com/openai/codex", G, O, C.TOOL, "OpenAI", 68, 120),
    entry("OpenCode Releases", "https://github.com/anomalyco/opencode", G, O, C.TOOL, "OpenCode", 65, 120),
    entry("Claude Code Releases", "https://github.com/anthropics/claude-code", G, O, C.TOOL, "Anthropic", 65, 180),
    entry("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", R, O, "", "Hugging Face", 60, 180),
    entry("Simon Willison", "https://simonwillison.net/atom/everything/", R, U, "", "", 65, 120),
    entry("Latent Space", "https://www.latent.space/feed", R, U, "", "", 56, 240),
    entry("One Useful Thing · Ethan Mollick", "https://www.oneusefulthing.org/feed", R, U, "", "", 56, 360),
    entry("SWE-bench Releases", "https://github.com/SWE-bench/SWE-bench", G, I, C.EVALUATION, "SWE-bench", 67, 360),
    entry("Artificial Analysis · 方法", "https://artificialanalysis.ai/methodology", W, I, C.EVALUATION, "Artificial Analysis", 68, 1440, "index,benchmark", "main", "Artificial Analysis 评测方法"),
    entry("GitHub Changelog", "https://github.blog/changelog/feed/", R, O, "", "GitHub", 63, 120, "copilot,models,student,free,credits"),
    entry("GitHub Student Developer Pack", "https://education.github.com/pack", W, O, C.OFFER, "GitHub", 80, 720, "copilot,credits,cloud,free", "main", "GitHub 学生开发者礼包"),
    entry("Gemini API 免费额度", "https://aistudio.google.com/docs/pricing.md", W, O, C.OFFER, "Google", 85, 720, "free tier,not available", "main", "Gemini API 免费额度与价格"),
    entry("Gemini API Changelog", "https://aistudio.google.com/docs/changelog.md", W, O, C.MODEL, "Google", 78, 240, "Gemini,preview", "main", "Gemini API 更新日志"),
    entry("Cursor for Students", "https://cursor.com/students", W, O, C.OFFER, "Cursor", 83, 720, "student,free,eligible,renew", "main", "Cursor 学生计划"),
    entry("OpenRouter Free Models", "https://openrouter.ai/docs/guides/routing/model-variants/free", W, O, C.OFFER, "OpenRouter", 74, 720, "free,limit,pricing", "main", "OpenRouter 免费模型与限制", enabled=False),
    entry("Cloudflare Workers AI Changelog", "https://developers.cloudflare.com/changelog/rss/workers-ai.xml", R, O, "", "Cloudflare", 68, 180, "free,workers ai,pricing,quota"),
    entry("Google Cloud Free Program", "https://cloud.google.com/free/docs/free-cloud-features", W, O, C.CLOUD, "Google Cloud", 83, 720, "free tier,e2-micro,always free,credit card", "main", "Google Cloud 免费套餐"),
    entry("Oracle Cloud Free Tier", "https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm", W, O, C.CLOUD, "Oracle Cloud", 82, 720, "always free,ampere,credit card", "article#Oracle_Cloud_Infrastructure_Free_Tier", "Oracle Cloud Always Free"),
    entry("Altare Plans", "https://docs.altare.gg/platform/plans", W, O, C.CLOUD, "Altare", 78, 720, "always free,postgres,team resources", "main", "Altare 免费云服务"),
    entry("Free for Developers", "https://github.com/ripienaar/free-for-dev", W, U, C.CLOUD, "", 53, 1440, "always free,free tier,free forever", "article.markdown-body", "Free for Developers · 目录变更"),
    entry("Hacker News · AI / 免费线索", "https://hnrss.org/newest?q=AI+free&points=15", R, U, "", "", 42, 240, enabled=False),
    entry("AI Free · 条款变更", "https://aifree.dev/changes?hub=student-ai-deals", W, U, C.OFFER, "", 58, 360, "student,credits,free", "main", "AI Free · 学生优惠线索"),
]

COMMUNITY_SOURCES = [
    entry("LINUX DO · 福利羊毛", "https://linux.do/c/welfare/36.rss", R, U, weight=58, interval=360,
          enabled=False, error="公开 RSS 测试返回 HTTP 403，可打开论坛版块查看。"),
    entry("LINUX DO · 科技资讯", "https://linux.do/c/news/34.rss", R, U, weight=52, interval=360,
          enabled=False, error="公开 RSS 测试返回 HTTP 403，可打开论坛版块查看。"),
    entry("吾爱破解 · 原创发布", "https://www.52pojie.cn/forum.php?mod=rss&fid=2", R, U, weight=54, interval=90),
    entry("V2EX · 分享创造", "https://www.v2ex.com/feed/create.xml", R, U, weight=57, interval=75),
    entry("V2EX · Google", "https://www.v2ex.com/feed/google.xml", R, U, weight=55, interval=90),
    entry("Free Inference · 试用与限免", "https://freeinference.dev/feed.xml", R, U, weight=52, interval=180,
          keywords="promo free,trial credits"),
    entry("Ollama Releases", "https://github.com/ollama/ollama", G, O, C.TOOL, "Ollama", 68, 120),
    entry("Open WebUI Releases", "https://github.com/open-webui/open-webui", G, O, C.TOOL, "Open WebUI", 66, 120),
    entry("OpenHands Releases", "https://github.com/OpenHands/OpenHands", G, O, C.TOOL, "OpenHands", 66, 180),
    entry("Qwen Code Releases", "https://github.com/QwenLM/qwen-code", G, O, C.TOOL, "Qwen", 66, 120),
    entry("Interconnects AI · Nathan Lambert", "https://www.interconnects.ai/feed", R, U, weight=57, interval=360,
          keywords="model,open weights,open-source,benchmark,eval,inference"),
]

X_AUTHOR_PROFILES = {
    "https://simonwillison.net/atom/everything/": "simonw",
    "https://www.latent.space/feed": "latentspacepod",
    "https://www.interconnects.ai/feed": "natolambert",
}
SOURCE_HOME_PAGES = {
    "https://linux.do/c/welfare/36.rss": "https://linux.do/c/welfare/36",
    "https://linux.do/c/news/34.rss": "https://linux.do/c/news/34",
    "https://www.52pojie.cn/forum.php?mod=rss&fid=2": "https://www.52pojie.cn/forum-2-1.html",
    "https://www.v2ex.com/feed/create.xml": "https://www.v2ex.com/go/create",
    "https://www.v2ex.com/feed/google.xml": "https://www.v2ex.com/go/google",
}
CATALOG_RELEASES = (("seed_v1", SOURCES), ("seed_v2_community", COMMUNITY_SOURCES))

OFFICIAL_DOMAINS = {
    "OpenAI": ("openai.com", "github.com/openai/"),
    "Anthropic": ("anthropic.com", "claude.com", "github.com/anthropics/"),
    "Google": ("google.com", "deepmind.google", "ai.google.dev"),
    "Qwen": ("qwenlm.github.io", "github.com/QwenLM/", "huggingface.co/Qwen/"),
    "DeepSeek": ("deepseek.com", "github.com/deepseek-ai/"),
    "Z.ai": ("z.ai",),
    "xAI": ("x.ai",),
    "OpenCode": ("opencode.ai", "github.com/anomalyco/", "github.com/sst/"),
    "Ollama": ("ollama.com", "github.com/ollama/ollama/"),
    "Open WebUI": ("openwebui.com", "github.com/open-webui/open-webui/"),
    "OpenHands": ("openhands.dev", "github.com/OpenHands/OpenHands/"),
    "Hugging Face": ("huggingface.co",),
    "GitHub": ("github.com/github/", "github.blog", "education.github.com"),
    "Cursor": ("cursor.com",),
    "OpenRouter": ("openrouter.ai",),
    "Cloudflare": ("cloudflare.com",),
    "Google Cloud": ("cloud.google.com",),
    "Oracle Cloud": ("oracle.com",),
    "Altare": ("altare.gg",),
}
