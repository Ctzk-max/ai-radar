import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone as utc
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.db import transaction
from django.utils import timezone

from .adapters import clean, date_value
from .catalog import OFFICIAL_DOMAINS
from .models import Category, Event, EventReference, Source

PROMO = r"free (?:tier|plan|credits?|tokens?|api|access|trial|subscription|for (?:students|developers|everyone)|months?|year|inference|usage)|student (?:discount|offer|plan|pack|benefits)|(?:credits?|discount) (?:for|to) (?:students|developers)|免费(?:额度|领取|会员|套餐|试用|调用|API|模型)|学生(?:优惠|福利|套餐)|赠金|限时免费"
CLOUD = r"\b(?:VPS|VM instances?|cloud compute|object storage|e2-micro|ampere a1|cloud hosting|serverless|database|postgres(?:ql)?|cloudflare|oracle cloud)\b|云服务器|免费云|对象存储|免费数据库"
FREE = r"\b(?:free|trial|no cost|always free)\b|免费|赠金|试用"
MODELS = r"\b(?:GPT(?:-[\w.]+)?|Claude|Gemini|DeepSeek|Qwen|GLM(?:-[\w.]+)?|Grok|LLM|model|model weights|ChatGPT|gpt-oss)\b|大模型|模型|上下文|推理"
CHANGES = r"\b(?:introduc\w*|launch\w*|releas\w*|updat\w*|new|deprecat\w*|upgrad\w*|availab\w*|API|pricing|context|token|weights|open source|open weight)\b|发布|新增|价格|开源|上线|更新"
EVAL = r"\b(?:benchmark|arena score|swe-bench|eval(?:uation)?s?|tokens per second|latency|hands-on|tested)\b|基准|实测|评测"
TOOLS = r"\b(?:Codex|OpenCode|Cursor|Copilot|Claude Code|Gemini CLI|agent harness|coding agent)\b|编程工具"
SPAM = r"sponsored post|affiliate roundup|buy followers|free followers|join our telegram|限时返利|推广返佣|点击下方广告"
STOP = {"the", "and", "with", "for", "from", "new", "now", "is", "of", "to", "a", "in", "our", "on"}
VERSION = re.compile(r"\b\d+(?:\.\d+)+(?:[-.][a-z0-9]+)*\b", re.I)


def terms(value):
    return list(dict.fromkeys(i.strip().casefold() for i in re.split(r"[,，;；\n]+", value) if i.strip()))


def keyword_hits(query, text):
    folded = text.casefold()
    return [term for term in terms(query) if term in folded]


def normalized(title):
    value = unicodedata.normalize("NFKC", title).casefold()
    return " ".join(re.findall(r"[a-z0-9]+(?:[.+-][a-z0-9]+)*|[\u3400-\u9fff]+", value))[:260]


def tokens(title):
    pieces = re.findall(r"[a-z0-9]+(?:[.+-][a-z0-9]+)*|[\u3400-\u9fff]+", title)
    result = set()
    for piece in pieces:
        if re.match(r"[\u3400-\u9fff]", piece):
            result.update(piece[i:i + 2] for i in range(max(1, len(piece) - 1)))
        elif piece not in STOP:
            result.add(piece)
    return result


def canonical(value):
    u = urlsplit(value)
    query = sorted((k, v) for k, v in parse_qsl(u.query) if not (k.casefold().startswith("utm_") or k.casefold() in {
        "fbclid", "gclid", "ref", "source", "mc_cid", "mc_eid",
    }))
    return urlunsplit(("https" if u.scheme == "https" else "http", u.netloc.lower(), u.path.rstrip("/") or "/", urlencode(query), ""))


def first_party(source, url):
    if source.trust != Source.Trust.OFFICIAL or not url.startswith("https://"):
        return False
    u = urlsplit(url)
    for entry in OFFICIAL_DOMAINS.get(source.platform, ()):
        host, _, owner = entry.partition("/")
        if owner:
            if u.hostname == host and u.path.casefold().startswith(f"/{owner.casefold()}"):
                return True
        elif u.hostname == host or u.hostname.endswith("." + host):
            return True
    return False


def infer_platform(title):
    for pattern, platform in [
        (r"\b(?:openai|chatgpt|codex|gpt[- ])", "OpenAI"), (r"\b(?:anthropic|claude)\b", "Anthropic"),
        (r"\b(?:gemini|deepmind|google ai)\b", "Google"), (r"\bdeepseek\b", "DeepSeek"),
        (r"\bqwen\b", "Qwen"), (r"\b(?:z\.ai|glm[- ])", "Z.ai"), (r"\b(?:xai|grok)\b", "xAI"),
        (r"\bcursor\b", "Cursor"), (r"\bopencode\b", "OpenCode"), (r"\bopenrouter\b", "OpenRouter"),
        (r"\bcloudflare\b", "Cloudflare"), (r"\b(?:github copilot|github student)\b", "GitHub"),
        (r"\boracle cloud\b", "Oracle Cloud"), (r"\bgoogle cloud\b", "Google Cloud"),
    ]:
        if re.search(pattern, title, re.I):
            return platform
    return ""


def classify(source, item):
    title = item.title
    text = f"{title} {item.summary[:2000]}"
    hits = keyword_hits(source.keywords, text)
    if not source.category and source.keywords and not hits:
        return None, 0
    if re.search(SPAM, text, re.I):
        return None, 0
    title_promo = bool(re.search(PROMO, title, re.I))
    promo = bool(re.search(PROMO, text, re.I))
    cloud = bool(re.search(CLOUD, text, re.I) and re.search(FREE, text, re.I))
    model = bool(re.search(MODELS, title, re.I))
    if source.category in {Category.OFFER, Category.CLOUD} and (item.snapshot or promo or cloud):
        category = source.category
    elif cloud and (re.search(CLOUD, title, re.I) or source.platform in {"Cloudflare", "Altare"}):
        category = Category.CLOUD
    elif title_promo or promo and (model or re.search(TOOLS, title, re.I)):
        category = Category.OFFER
    elif source.category == Category.EVALUATION or re.search(EVAL, title, re.I) and (model or re.search(TOOLS, text, re.I)):
        category = Category.EVALUATION
    elif source.category == Category.MODEL or model and re.search(CHANGES, text, re.I):
        category = Category.MODEL
    elif source.category == Category.TOOL or re.search(TOOLS, title, re.I):
        category = Category.TOOL
    else:
        return None, 0
    score = (20 if category == Category.OFFER else 13 if category == Category.CLOUD else 3)
    score += (10 if source.trust == Source.Trust.OFFICIAL else 4 if source.trust == Source.Trust.INDEPENDENT else 0)
    score += min(14, len(hits) * 3)
    if source.kind == Source.Kind.GITHUB and re.search(r"(?:^|[-.])(?:alpha|beta|rc|nightly|canary)[.-]?", title, re.I):
        return None, 0
    return category, min(100, source.weight + score)


DETAILS = [
    ("benefit", "免费内容与额度", PROMO),
    ("term", "免费期限", r"\b(?:always free|free forever|[0-9]+[ -](?:months?|days?|years?))\b|永久免费|\d+\s*(?:个月|年|天)"),
    ("region", "地区", r"eligible (?:countries|regions)|(?:only |available )in (?:the )?(?:US|UK|United States|Europe|Canada|India)\b|countries and territories|仅限.{2,35}地区"),
    ("student", "学生要求", r"\b(?:students?|academic status|student verification|school email|education email)\b|在校生|学生"),
    ("card", "信用卡", r"\b(?:credit card|payment card|debit card|payment method)\b|信用卡|银行卡"),
    ("new_user", "新用户限制", r"\b(?:new (?:users?|customers?|subscribers?|accounts?)|first-time|existing customers)\b|仅限新用户|首次注册"),
    ("renewal", "续费与收费", r"\b(?:auto(?:matic(?:ally)?)?[- ]?renew\w*|charged|charge your|billing starts|after (?:the |your )?trial|upgrade to paid)\b|自动续费|到期.{0,10}收费|超额.{0,8}计费"),
    ("procedure", "领取方法", r"\b(?:sign up|apply for|redeem|claim your|verify your|register|activate)\b|申请|注册|激活|领取"),
    ("cpu", "CPU", r"\d+(?:\.\d+)?\s*(?:vCPUs?|OCPUs?|CPU cores?|Arm cores?)|\d+\s*核"),
    ("ram", "RAM", r"\d+(?:\.\d+)?\s*(?:[GM]i?B)\s+(?:of\s+)?(?:RAM|memory)|(?:RAM|memory)\W{1,6}\d+(?:\.\d+)?\s*[GM]i?B"),
    ("disk", "磁盘或对象存储", r"\d+(?:\.\d+)?\s*(?:[GMT]i?B)\s+(?:of\s+)?(?:disk|storage|SSD|block storage)"),
    ("traffic", "流量", r"\d+(?:\.\d+)?\s*(?:[GMT]i?B)\s+(?:of\s+)?(?:outbound|egress|bandwidth|data transfer)"),
]


def excerpt(pattern, value):
    match = re.search(pattern, value, re.I)
    if not match:
        return ""
    start = max(value.rfind(" … ", 0, match.start()), value.rfind(". ", 0, match.start()))
    end = [i for sep in (" … ", ". ") if (i := value.find(sep, match.end())) != -1]
    left = max(start + 1 if start >= 0 else 0, match.start() - 55)
    right = min(min(end, default=len(value)), match.end() + 90)
    return value[left:right].strip(" …. ")


def explicit_date(pattern, text):
    found = re.search(pattern + r"[ :：]*(20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2}))?)", text, re.I)
    if not found:
        return None
    value = found.group(1)
    # A calendar date without timezone/time is not interpreted as an exact cutoff.
    return date_value(value) if "T" in value else None


def offer_evidence(item, verified):
    text = item.summary
    data = {key: value for key, label, pattern in DETAILS if (value := excerpt(pattern, text))}
    ongoing = bool(item.snapshot and re.search(r"\balways free\b|\bfree forever\b|永久免费", text, re.I))
    ended = bool(re.search(r"(?:this |the )(?:offer|promotion|program) (?:has ended|is no longer available)|活动已结束", text, re.I))
    data["ongoing"] = verified and ongoing and not ended
    data["ended"] = verified and ended
    if verified:
        data["official_url"] = item.url
    return data, explicit_date(r"(?:starts? on|begins? on|开始时间)", text), explicit_date(
        r"(?:expires(?: on)?|ends on|valid until|apply by|截止时间)", text)


def similar(category, platform, item, norm, cutoff):
    pool = Event.objects.filter(category=category, discovered_at__gte=cutoff, title__isnull=False)
    if platform:
        pool = pool.filter(platform__in=[platform, ""])
    if item.snapshot or len(norm) < 15:
        return None
    a = tokens(norm)
    version = set(VERSION.findall(item.title))
    for event in pool.order_by("-discovered_at")[:250]:
        if item.url == event.canonical_url:
            continue
        if version != set(VERSION.findall(event.title)):
            continue
        if norm == event.normalized:
            return event
        b = tokens(event.normalized)
        if len(a & b) >= 4 and len(a & b) / max(1, len(a | b)) >= 0.72:
            return event
    return None


def ingest(source, items, now=None):
    """Called within the source result transaction, with the shared ingest row locked."""
    now = now or timezone.now()
    added = 0
    for item in items:
        if item.published:
            if item.published > now + timedelta(hours=24) or item.published < now - timedelta(days=365):
                continue
        category, score = classify(source, item)
        if not category:
            continue
        url = canonical(item.url)
        digest = hashlib.sha256((url + item.version).encode()).hexdigest()
        reference = EventReference.objects.select_related("event").filter(digest=digest).first()
        event = reference.event if reference else None
        platform = source.platform or infer_platform(item.title)
        norm = normalized(item.title)
        is_offer = category in {Category.OFFER, Category.CLOUD}
        verified = first_party(source, item.url) and (not is_offer or bool(re.search(PROMO + "|" + FREE, item.summary, re.I)))
        if reference and reference.source_id == source.pk:
            if verified and is_offer and (not event.checked_at or event.checked_at < now - timedelta(days=1)):
                Event.objects.filter(pk=event.pk).update(checked_at=now)
            continue
        if not event:
            event = similar(category, platform, item, norm, now - timedelta(days=9))
        if not event and not item.snapshot:
            for alternate in item.links:
                if alternate == item.url or not infer_platform(item.title):
                    continue
                existing = Event.objects.filter(canonical_url=canonical(alternate), category=category, platform=platform).first()
                if existing and len(tokens(norm) & tokens(existing.normalized)) >= 3:
                    event = existing
                    break
        if event is None:
            event = Event.objects.create(
                title=clean(item.title, 260), normalized=norm, summary=clean(item.summary),
                category=category, platform=platform, canonical_url=url,
                published_at=item.published, discovered_at=now, priority=score,
            )
            added += 1
        elif score > event.priority:
            event.priority = score
        if verified:
            event.first_party = True
            event.checked_at = now
            event.canonical_url = url
            event.platform = platform
            event.summary = clean(item.summary) or event.summary
        if is_offer and (verified or not event.first_party):
            evidence, begins, ends = offer_evidence(item, verified)
            event.evidence = evidence or event.evidence
            event.starts_at, event.deadline = begins, ends
        event.save(update_fields=["priority", "first_party", "checked_at", "canonical_url", "platform",
                                  "summary", "evidence", "starts_at", "deadline"])
        association = digest if not reference else hashlib.sha256(f"{digest}:{source.pk}".encode()).hexdigest()
        EventReference.objects.get_or_create(digest=association, defaults={
            "event": event, "source": source, "source_name": source.name, "url": url,
            "trust": Source.Trust.OFFICIAL if verified else (
                Source.Trust.INDEPENDENT if source.trust == Source.Trust.INDEPENDENT else Source.Trust.COMMUNITY),
        })
    return added
