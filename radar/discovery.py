from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from .adapters import collect_source
from .intelligence import classify
from .models import Discovery, Runtime, Source
from .network import FetchError, public_url

IGNORED = {"twitter.com", "x.com", "youtube.com", "youtu.be", "linkedin.com", "discord.com", "t.me", "facebook.com",
           "microsoft.com", "apple.com", "wikipedia.org", "arxiv.org", "githubassets.com", "githubusercontent.com"}


def discovery_url(link):
    try:
        target = urlsplit(public_url(link, source=True))
    except FetchError:
        return ""
    if target.scheme != "https" or any(target.hostname == host or target.hostname.endswith("." + host) for host in IGNORED):
        return ""
    if target.hostname == "github.com":
        parts = target.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] not in {"features", "topics", "orgs", "marketplace", "sponsors", "collections"}:
            return f"https://github.com/{parts[0]}/{parts[1]}"
        return ""
    if target.path.endswith((".xml", ".rss", ".atom")):
        return f"https://{target.hostname}{target.path}"
    return f"https://{target.hostname}/"


def enqueue_candidates(source, items, now):
    if source.weight < 60 or source.kind == Source.Kind.X or Discovery.objects.count() >= 240:
        return
    existing = set(Source.objects.values_list("url", flat=True))
    hosts = {urlsplit(url).hostname for url in existing}
    candidates = {}
    for item in items:
        if not item.published or item.published < now - timedelta(days=14) or not classify(source, item)[0]:
            continue
        for value in (*item.links, item.url):
            target = discovery_url(value)
            if target and target not in existing:
                host = urlsplit(target).hostname
                if host not in hosts or host == "github.com":
                    candidates[target] = Discovery(url=target, found_from=source.name)
            if len(candidates) >= 5:
                break
        if len(candidates) >= 5:
            break
    Discovery.objects.bulk_create(candidates.values(), ignore_conflicts=True)


def assess_candidates():
    now = timezone.now()
    cutoff = now - timedelta(hours=24)
    with transaction.atomic():
        slot, created = Runtime.objects.select_for_update().get_or_create(pk="discovery_try", defaults={"at": now})
        if not created and slot.at >= cutoff:
            return 0
        candidates = list(Discovery.objects.filter(status="pending").order_by("found_at")[:4])
        if not candidates:
            if created:
                slot.delete()
            return 0
        slot.at = now
        slot.save(update_fields=["at"])
    for candidate in candidates:
        status = "rejected"
        try:
            source = Source(url=candidate.url, name=candidate.found_from, trust=Source.Trust.COMMUNITY)
            batch = collect_source(source)
            candidate.detected_kind = batch.kind
            matches = [item for item in batch.items if item.published and item.published >= now - timedelta(days=120)
                       and classify(source, item)[0]]
            candidate.items = len(matches)
            candidate.sample_titles = [item.title for item in matches[:3]]
            if batch.kind in {Source.Kind.RSS, Source.Kind.GITHUB} and len(matches) >= 2:
                status = "ready"
            else:
                candidate.error = "公开订阅近期相关条目少于两条，或网页没有可追溯的订阅渠道"
        except FetchError as error:
            candidate.error = str(error)
        except (TypeError, ValueError):
            candidate.error = "来源格式无法识别"
        Discovery.objects.filter(pk=candidate.pk, status="pending").update(
            status=status, error=candidate.error[:300], checked_at=timezone.now(), items=candidate.items,
            sample_titles=candidate.sample_titles, detected_kind=candidate.detected_kind,
        )
    return len(candidates)
