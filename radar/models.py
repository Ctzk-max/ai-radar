from django.db import models
from django.utils import timezone


class Category(models.TextChoices):
    OFFER = "offer", "AI 羊毛"
    MODEL = "model", "模型动态"
    EVALUATION = "evaluation", "模型评测"
    CLOUD = "cloud", "免费云"
    TOOL = "tool", "开发工具"


class Source(models.Model):
    class Kind(models.TextChoices):
        AUTO = "auto", "自动识别"
        RSS = "rss", "RSS / Atom"
        GITHUB = "github", "GitHub Releases"
        WEB = "web", "公开网页"
        X = "x", "X 公开账号"

    class Trust(models.TextChoices):
        OFFICIAL = "official", "平台官方"
        INDEPENDENT = "independent", "独立测试"
        COMMUNITY = "community", "社区线索"

    name = models.CharField(max_length=110)
    url = models.URLField(max_length=1200, unique=True)
    kind = models.CharField(max_length=12, choices=Kind, default=Kind.AUTO)
    trust = models.CharField(max_length=16, choices=Trust, default=Trust.COMMUNITY)
    category = models.CharField(max_length=15, choices=Category, blank=True)
    platform = models.CharField(max_length=65, blank=True)
    weight = models.PositiveSmallIntegerField(default=50)
    interval = models.PositiveIntegerField(default=120)
    keywords = models.CharField(max_length=500, blank=True)
    enabled = models.BooleanField(default=True)
    follow = models.BooleanField(default=False)
    bridge_url = models.URLField(max_length=1200, blank=True)
    selector = models.CharField(max_length=170, blank=True)
    page_title = models.CharField(max_length=160, blank=True)
    detected_kind = models.CharField(max_length=12, blank=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    next_check = models.DateTimeField(default=timezone.now, db_index=True)
    streak = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)
    last_count = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    etag = models.CharField(max_length=300, blank=True)
    last_modified = models.CharField(max_length=140, blank=True)
    fetch_url = models.URLField(max_length=1200, blank=True)
    fingerprints = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    class Claim(models.TextChoices):
        OPEN = "open", "未领取"
        CLAIMED = "claimed", "已领取"
        SKIP = "skip", "暂不考虑"
        INELIGIBLE = "ineligible", "不符合资格"
        EXPIRED = "expired", "已过期"

    title = models.CharField(max_length=260)
    normalized = models.CharField(max_length=260, db_index=True)
    summary = models.CharField(max_length=1300, blank=True)
    category = models.CharField(max_length=15, choices=Category, db_index=True)
    platform = models.CharField(max_length=65, blank=True, db_index=True)
    canonical_url = models.URLField(max_length=1200)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    discovered_at = models.DateTimeField(default=timezone.now, db_index=True)
    priority = models.SmallIntegerField(default=0)
    first_party = models.BooleanField(default=False)
    evidence = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    bookmarked = models.BooleanField(default=False, db_index=True)
    read = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False)
    claim = models.CharField(max_length=12, choices=Claim, default=Claim.OPEN, db_index=True)
    claim_note = models.CharField(max_length=800, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)

    def eligibility(self):
        if not self.first_party:
            return "尚未核实", "warning"
        now = timezone.now()
        if self.deadline and self.deadline <= now or self.evidence.get("ended"):
            return "已结束", "muted"
        if self.starts_at and self.starts_at > now:
            return "尚未开始", "muted"
        if self.deadline:
            if (self.deadline - now).total_seconds() <= 72 * 3600:
                return "即将截止", "warning"
            return "可以领取", "success"
        if self.evidence.get("ongoing"):
            return "可以领取", "success"
        return "时间未知", "muted"


class EventReference(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="references")
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, related_name="references")
    source_name = models.CharField(max_length=110)
    trust = models.CharField(max_length=16, choices=Source.Trust)
    url = models.URLField(max_length=1200)
    digest = models.CharField(max_length=64, unique=True)
    found_at = models.DateTimeField(default=timezone.now)


class FetchRun(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=14)
    parsed = models.PositiveIntegerField(default=0)
    added = models.PositiveIntegerField(default=0)
    elapsed_ms = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)


class Preferences(models.Model):
    interests = models.CharField(max_length=800, blank=True)
    blocked_platforms = models.CharField(max_length=800, blank=True)
    blocked_categories = models.JSONField(default=list, blank=True)
    hide_read = models.BooleanField(default=False)
    dark = models.CharField(max_length=10, default="system")


class Runtime(models.Model):
    key = models.CharField(max_length=20, primary_key=True)
    at = models.DateTimeField(default=timezone.now)


class Discovery(models.Model):
    url = models.URLField(max_length=1200, unique=True)
    found_from = models.CharField(max_length=110)
    found_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=12, default="pending", db_index=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    detected_kind = models.CharField(max_length=12, blank=True)
    items = models.PositiveSmallIntegerField(default=0)
    sample_titles = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=300, blank=True)


class LoginWindow(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)


class Observation(models.Model):
    class Dimension(models.TextChoices):
        CODING = "coding", "编程"
        AGENT = "agent", "Agent"
        REASONING = "reasoning", "数学与推理"
        WRITING = "writing", "学术写作"
        CONTEXT = "context", "长上下文"
        MEDIA = "multimodal", "多模态"
        SPEED = "speed", "速度"
        COST = "cost", "API 成本"
        LIMITS = "limits", "使用限制"
        EXPERIENCE = "experience", "社区体验"

    model = models.CharField(max_length=110, db_index=True)
    dimension = models.CharField(max_length=15, choices=Dimension, db_index=True)
    metric = models.CharField(max_length=140)
    value = models.CharField(max_length=160)
    unit = models.CharField(max_length=35, blank=True)
    method = models.CharField(max_length=800)
    trust = models.CharField(max_length=16, choices=Source.Trust)
    url = models.URLField(max_length=1200)
    observed_on = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["model", "dimension", "metric", "url", "observed_on"], name="unique_observation")]
