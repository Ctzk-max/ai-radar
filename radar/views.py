import hashlib
import json
import logging
import os
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.serializers.base import DeserializationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Case, Exists, F, OuterRef, Q, Value, When
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .adapters import collect_source
from .backup import export_backup, preferences_row, read_json, restore_backup, source_configuration
from .forms import ClaimForm, ObservationForm, PreferenceForm, SOURCE_FIELDS, SourceForm, TestSourceForm
from .intelligence import DETAILS, terms
from .models import Category, Event, EventReference, FetchRun, LoginWindow, Observation, Runtime, Source
from .network import FetchError
from .security import auth_version, authenticated, private, verify_password

log = logging.getLogger(__name__)
SECTIONS = {
    "all": "全部精选", "offer": "AI 羊毛", "model": "模型动态", "cloud": "免费云服务器",
    "evaluation": "模型评测动态", "tool": "开发工具", "saved": "我的收藏", "claims": "领取记录", "history": "历史记录",
}
HELP = {
    "all": "模型更新、免费额度和云服务机会，按重要程度整理。",
    "offer": "汇总免费额度、试用及学生计划，查看领取条件与核验记录。",
    "model": "追踪模型发布、能力变化、API 价格与平台限制。",
    "cloud": "查看免费算力、数据库及存储的适用条件与条款变更。",
    "saved": "收藏的重要情报会保留在这里。",
    "claims": "查看已填写领取状态或备注的福利。",
    "history": "查看归档情报与个人反馈记录。",
}


def page(request, template, context=None, *, status=200):
    ctx = {"active": "", "theme": "system", "signed_in": authenticated(request)}
    if ctx["signed_in"]:
        ctx["theme"] = preferences_row().dark
    ctx.update(context or {})
    return render(request, template, ctx, status=status)


def number(value, default, minimum, maximum):
    try:
        return max(minimum, min(maximum, int(value)))
    except (ValueError, TypeError):
        return default


def valid_origin(request):
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return False
    origin = request.headers.get("Origin")
    expected = settings.PUBLIC_URL if settings.PRODUCTION else f"{request.scheme}://{request.get_host()}"
    return origin is None or origin == expected


@transaction.atomic
def login_attempt(request):
    stamp = timezone.now()
    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = hashlib.sha256((settings.SECRET_KEY + ":login:" + ip).encode()).hexdigest()
    keys = ("global", key)
    rows = [LoginWindow.objects.select_for_update().get_or_create(pk=k, defaults={"at": stamp})[0] for k in keys]
    for row, limit in zip(rows, (24, 12)):
        if row.at <= stamp - timedelta(minutes=12):
            row.at, row.attempts = stamp, 0
        if row.attempts >= limit:
            return None
    for row in rows:
        row.attempts += 1
        row.save(update_fields=["at", "attempts"])
    return key


@require_http_methods(["GET", "POST"])
def login(request):
    if authenticated(request):
        return redirect("feed")
    if request.method == "GET":
        return page(request, "radar/login.html")
    if not valid_origin(request):
        return HttpResponse(status=403)
    key = login_attempt(request)
    if key is None:
        response = page(request, "radar/login.html", {"error": "尝试次数过多，请稍后重试。"}, status=429)
        response["Retry-After"] = "720"
        return response
    if not verify_password(request.POST.get("password", "")):
        return page(request, "radar/login.html", {"error": "密码不正确。"}, status=400)
    LoginWindow.objects.filter(pk__in=["global", key]).delete()
    request.session.cycle_key()
    request.session["radar_admin"] = auth_version()
    from django.middleware.csrf import rotate_token
    rotate_token(request)
    return redirect("feed")


@private
@require_POST
def logout(request):
    request.session.flush()
    return redirect("login")


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    version = os.getenv("ALTARE_GIT_COMMIT_SHA", "")
    return JsonResponse({"status": "ok", **({"version": version[:12]} if version else {})})


@require_GET
def manifest(request):
    return JsonResponse({
        "id": "/", "name": "AI Radar", "short_name": "AI Radar", "start_url": "/", "display": "standalone",
        "lang": "zh-Hans", "background_color": "#f5f7fb", "theme_color": "#11182d",
        "icons": [{"src": static(f"radar/icon-{size}.png"), "sizes": f"{size}x{size}", "type": "image/png", "purpose": "any maskable"} for size in (192, 512)],
    }, content_type="application/manifest+json")


@require_GET
def service_worker(request):
    return HttpResponse(
        "self.addEventListener('install', () => self.skipWaiting());\n"
        "self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));\n"
        "self.addEventListener('fetch', event => {\n"
        "  if (event.request.mode === 'navigate') event.respondWith(fetch(event.request).catch(() =>\n"
        "    new Response('AI Radar offline', {status: 503, headers: {'Content-Type': 'text/plain', 'Cache-Control': 'no-store'}})));\n"
        "});\n",
        content_type="text/javascript",
    )

def filtered(request):
    params = request.GET
    section = params.get("section", "all")
    section = section if section in SECTIONS else "all"
    default_days = 0 if section in {"saved", "claims", "history"} else 3
    days = number(params.get("days"), default_days, 0, 3650)
    order = params.get("order", "priority")
    order = order if order in {"priority", "new", "deadline"} else "priority"
    search = params.get("q", "").strip()[:120]
    filters = {
        "section": section, "q": search, "days": days, "order": order,
        "platform": params.get("platform", "")[:65], "trust": params.get("trust", "")[:16],
        "read": params.get("read", "")[:12],
    }
    profile = preferences_row()
    items = Event.objects.annotate(moment=Coalesce("published_at", "discovered_at"))
    if section == "saved":
        items = items.filter(bookmarked=True)
    elif section == "claims":
        items = items.exclude(claim=Event.Claim.OPEN, claim_note="")
    elif section != "history":
        items = items.filter(hidden=False)
        if profile.hide_read and filters["read"] != "read":
            items = items.filter(Q(read=False) | Q(pinned=True))
        if profile.blocked_categories:
            items = items.exclude(category__in=profile.blocked_categories)
        for platform in terms(profile.blocked_platforms)[:25]:
            items = items.exclude(platform__iexact=platform)
    if section in Category.values:
        items = items.filter(category=section)
    if days:
        items = items.filter(moment__gte=timezone.now() - timedelta(days=days))
    if filters["platform"]:
        items = items.filter(platform__iexact=filters["platform"])
    if filters["trust"] == "official":
        items = items.filter(first_party=True)
    elif filters["trust"] in {Source.Trust.COMMUNITY, Source.Trust.INDEPENDENT}:
        items = items.filter(first_party=False).filter(Exists(EventReference.objects.filter(
            event_id=OuterRef("pk"), trust=filters["trust"])))
    if filters["read"] in {"read", "unread"}:
        items = items.filter(read=filters["read"] == "read")
    for term in search.split()[:8]:
        items = items.filter(Q(title__icontains=term) | Q(summary__icontains=term) | Q(platform__icontains=term) |
                             Exists(EventReference.objects.filter(event_id=OuterRef("pk"), source_name__icontains=term)))
    if order == "priority":
        follow = EventReference.objects.filter(event_id=OuterRef("pk"), source__follow=True)
        feedback = Event.objects.filter(hidden=True, platform=OuterRef("platform"), category=OuterRef("category"), platform__gt="")
        score = F("priority") + Case(When(Exists(follow), then=Value(18)), default=Value(0))
        score += Case(When(Exists(feedback), then=Value(-16)), default=Value(0))
        score += Case(When(deadline__lt=timezone.now(), then=Value(-45)), When(claim=Event.Claim.EXPIRED, then=Value(-45)),
                      When(claim=Event.Claim.CLAIMED, then=Value(-20)), When(claim=Event.Claim.INELIGIBLE, then=Value(-26)),
                      default=Value(0))
        score += Case(When(moment__gte=timezone.now() - timedelta(days=1), then=Value(7)), default=Value(0))
        for term in terms(profile.interests)[:12]:
            score += Case(When(Q(title__icontains=term) | Q(summary__icontains=term), then=Value(9)), default=Value(0))
        items = items.annotate(rank=score).order_by("-pinned", "-rank", "-moment", "-pk")
    elif order == "deadline":
        items = items.order_by("-pinned", Case(When(deadline__gte=timezone.now(), then=Value(0)), default=Value(1)),
                               F("deadline").asc(nulls_last=True), "-moment", "-pk")
    else:
        items = items.order_by("-pinned", "-moment", "-pk")
    return items, filters


def badge_for(event):
    if event.category in {Category.OFFER, Category.CLOUD}:
        return event.eligibility()
    refs = list(event.references.all())
    if event.first_party:
        return "官方来源", "success"
    if any(ref.trust == Source.Trust.INDEPENDENT for ref in refs):
        return "独立来源", "info"
    return "社区线索", "muted"


def card(event):
    event.badge, event.tone = badge_for(event)
    event.details = [(label, event.evidence.get(key, "")) for key, label, pattern in DETAILS]
    return event


@private
@require_GET
def feed(request):
    items, filters = filtered(request)
    paginator = Paginator(items.prefetch_related("references"), 24)
    result = paginator.get_page(request.GET.get("page"))
    result.object_list = [card(event) for event in result.object_list]
    section = filters["section"]
    group = Event.objects.filter(discovered_at__gte=timezone.now() - timedelta(days=3), hidden=False)
    stats = [
        ("offer", "羊毛机会", group.filter(category=Category.OFFER).count()),
        ("model", "模型动态", group.filter(category=Category.MODEL).count()),
        ("cloud", "免费云", group.filter(category=Category.CLOUD).count()),
        ("saved", "已收藏", Event.objects.filter(bookmarked=True).count()),
    ]
    return page(request, "radar/feed.html", {
        "active": section, "title": SECTIONS[section], "subtitle": HELP.get(section, "查看已采集的更新和来源证据。"),
        "filters": filters, "stats": stats, "results": result, "count": paginator.count,
        "query": urlencode(filters), "platforms": Event.objects.exclude(platform="").order_by("platform").values_list("platform", flat=True).distinct(),
        "counts_range": "近 3 天发现", "heartbeat": Runtime.objects.filter(pk="heartbeat").values_list("at", flat=True).first(),
    })


@private
@require_GET
def api_feed(request):
    items, filters = filtered(request)
    paginator = Paginator(items.prefetch_related("references"), 24)
    result = paginator.get_page(request.GET.get("page"))
    return JsonResponse({
        "count": paginator.count, "page": result.number, "filters": filters,
        "items": [{
            "id": event.pk, "title": event.title, "summary": event.summary, "category": event.category,
            "platform": event.platform, "url": event.canonical_url, "published_at": event.published_at,
            "discovered_at": event.discovered_at, "bookmarked": event.bookmarked, "status": badge_for(event)[0],
            "sources": [{"name": ref.source_name, "url": ref.url, "trust": ref.trust} for ref in event.references.all()],
        } for event in result.object_list],
    })


@private
@require_GET
def event_detail(request, event_id):
    event = card(get_object_or_404(Event.objects.prefetch_related("references"), pk=event_id))
    return page(request, "radar/event.html", {"title": event.title, "event": event, "claim_form": ClaimForm(instance=event)})


@private
@require_POST
def event_update(request, event_id):
    action = request.POST.get("action")
    if action in {"bookmarked", "read", "pinned", "hidden"}:
        with transaction.atomic():
            event = get_object_or_404(Event.objects.select_for_update(), pk=event_id)
            setattr(event, action, not getattr(event, action))
            event.save(update_fields=[action])
    elif action == "claim":
        with transaction.atomic():
            event = get_object_or_404(Event.objects.select_for_update(), pk=event_id,
                                      category__in=[Category.OFFER, Category.CLOUD])
            form = ClaimForm(request.POST, instance=event)
            if not form.is_valid():
                return page(request, "radar/event.html", {"title": event.title, "event": card(event), "claim_form": form}, status=400)
            saved = form.save(commit=False)
            saved.claimed_at = (saved.claimed_at or timezone.now()) if saved.claim == Event.Claim.CLAIMED else None
            saved.save(update_fields=["claim", "claim_note", "claimed_at"])
            messages.success(request, "已更新领取记录。")
    else:
        return HttpResponse(status=400)
    if request.POST.get("return_section") in SECTIONS:
        query = urlencode({key: request.POST[key][:160] for key in ["section", "q", "days", "order", "platform", "trust", "read", "page"] if key in request.POST})
        return redirect(reverse("feed") + "?" + query)
    return redirect("event", event_id=event_id)


@private
@require_GET
def sources(request):
    sources = Source.objects.order_by("-follow", "-enabled", "-weight", "name")
    q = request.GET.get("q", "").strip()[:100]
    if q:
        sources = sources.filter(Q(name__icontains=q) | Q(platform__icontains=q) | Q(url__icontains=q))
    return page(request, "radar/sources.html", {
        "title": "来源管理", "active": "sources", "sources": Paginator(sources, 40).get_page(request.GET.get("page")), "q": q,
        "test_form": TestSourceForm(),
    })


@private
@require_http_methods(["GET", "POST"])
def source_edit(request, source_id=None):
    source = get_object_or_404(Source, pk=source_id) if source_id else None
    form = SourceForm(request.POST or None, instance=source)
    if request.method == "POST" and form.is_valid():
        if source_id:
            with transaction.atomic():
                locked = get_object_or_404(Source.objects.select_for_update(), pk=source_id)
                form.instance.pk = locked.pk
                for name in SOURCE_FIELDS:
                    setattr(locked, name, getattr(form.instance, name))
                locked.revision += 1
                locked.lease_until = None
                locked.next_check = timezone.now()
                for field in ("etag", "last_modified", "fetch_url", "detected_kind", "error"):
                    setattr(locked, field, "")
                locked.streak = 0
                if set(form.changed_data) & {"url", "kind", "selector", "bridge_url", "keywords"}:
                    locked.fingerprints = []
                locked.save()
        else:
            form.save()
        messages.success(request, "来源已保存。")
        return redirect("sources")
    return page(request, "radar/form.html", {
        "title": "编辑来源" if source else "添加来源", "active": "sources", "form": form,
        "hint": "可直接粘贴 RSS、GitHub 仓库、公开网页或 X 账号地址。添加来源后可在列表发起检查。", "back_name": "sources",
    }, status=400 if request.method == "POST" else 200)


@private
@require_POST
def source_action(request, source_id):
    with transaction.atomic():
        source = get_object_or_404(Source.objects.select_for_update(), pk=source_id)
        action = request.POST.get("action")
        if action == "delete":
            if request.POST.get("confirm") != "delete":
                return page(request, "radar/source_delete.html", {"title": "删除来源", "source": source, "active": "sources"})
            source.delete()
            messages.success(request, "来源已删除。")
        elif action == "toggle":
            source.enabled = not source.enabled
            source.next_check = timezone.now()
            source.revision += 1
            source.lease_until = None
            source.save(update_fields=["enabled", "next_check", "revision", "lease_until"])
            messages.success(request, "已恢复采集。" if source.enabled else "已暂停采集。")
        elif action == "follow":
            source.follow = not source.follow
            source.save(update_fields=["follow"])
        elif action == "queue":
            if source.enabled:
                source.next_check = timezone.now()
                source.save(update_fields=["next_check"])
                messages.success(request, "已加入采集队列。请在采集状态查看结果。")
            else:
                messages.info(request, "恢复来源后才能加入采集队列。")
        else:
            return HttpResponse(status=400)
    return redirect("sources")


@private
@require_POST
def source_test(request):
    form = TestSourceForm(request.POST)
    result = None
    error = ""
    if form.is_valid():
        try:
            result = collect_source(Source(name="测试来源", **form.cleaned_data))
        except FetchError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"解析异常（{type(exc).__name__}）"
    return page(request, "radar/source_test.html", {"title": "测试抓取", "active": "sources", "form": form, "result": result, "error": error})


@private
@require_POST
def sources_import(request):
    try:
        if "file" not in request.FILES:
            raise ValueError("请选择来源配置文件")
        data = read_json(request.FILES["file"], 512 * 1024)
        if isinstance(data, dict):
            if data.get("schema") != 1 or data.get("kind") != "ai-radar-sources":
                raise ValueError("来源配置版本未知")
            data = data.get("sources")
        if not isinstance(data, list) or not 0 < len(data) <= 200:
            raise ValueError("来源配置须包含 1–200 条记录")
        added = skipped = 0
        with transaction.atomic():
            for index, record in enumerate(data, 1):
                if not isinstance(record, dict):
                    raise ValueError(f"第 {index} 条格式无效")
                values = {"weight": 50, "interval": 120, "kind": Source.Kind.AUTO, "trust": Source.Trust.COMMUNITY,
                          "enabled": True, **{key: record[key] for key in SOURCE_FIELDS if key in record}}
                from .forms import clean_url
                url = clean_url(values.get("url", ""), source=True)
                if Source.objects.filter(url=url).exists():
                    skipped += 1
                    continue
                form = SourceForm(values)
                if not form.is_valid():
                    raise ValueError(f"第 {index} 条无效：{'、'.join(form[field].label for field in form.errors)}")
                form.save()
                added += 1
        messages.success(request, f"已添加 {added} 个来源，跳过 {skipped} 个现有链接。")
    except (ValueError, IntegrityError, FetchError, UnicodeError) as exc:
        messages.error(request, str(exc) if isinstance(exc, ValueError) else "来源导入失败，请检查配置文件。")
    except Exception:
        messages.error(request, "公开来源 URL 或配置字段无效。")
    return redirect("sources")


def status_data():
    sources = Source.objects.all()
    live = sources.filter(enabled=True)
    recent = FetchRun.objects.order_by("-at").first()
    beats = dict(Runtime.objects.filter(pk__in=["heartbeat", "benchmark_try", "benchmark_ok"]).values_list("pk", "at"))
    active = beats.get("heartbeat")
    return {
        "total": sources.count(), "healthy": live.filter(streak=0, last_success__isnull=False).count(),
        "failed": live.filter(streak__gt=0).count(), "paused": sources.filter(enabled=False).count(),
        "last_run": recent.at if recent else None, "last_success": live.exclude(last_success=None).order_by("-last_success").values_list("last_success", flat=True).first(),
        "heartbeat": active, "worker_ok": bool(active and active > timezone.now() - timedelta(minutes=4)),
        "benchmark_last_success": beats.get("benchmark_ok"), "benchmark_last_attempt": beats.get("benchmark_try"),
    }


@private
@require_GET
def status_page(request):
    return page(request, "radar/status.html", {
        "title": "采集状态", "active": "status", "metrics": status_data(),
        "sources": Source.objects.order_by("-enabled", "-streak", "-weight")[:200],
        "runs": FetchRun.objects.select_related("source").order_by("-at")[:25],
    })


@private
@require_GET
def api_status(request):
    return JsonResponse(status_data())


@private
@require_http_methods(["GET", "POST"])
def preferences(request):
    config = preferences_row()
    form = PreferenceForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "偏好已保存。")
        return redirect("settings")
    return page(request, "radar/settings.html", {"title": "设置", "active": "settings", "form": form})


@private
@require_GET
def export_data(request, kind):
    if kind == "sources":
        body = {"schema": 1, "kind": "ai-radar-sources", "sources": [source_configuration(s) for s in Source.objects.order_by("pk")]}
    elif kind == "bookmarks":
        body = {"schema": 1, "kind": "ai-radar-bookmarks", "events": list(Event.objects.filter(bookmarked=True).values(
            "title", "category", "platform", "canonical_url", "published_at", "discovered_at", "claim", "claim_note", "claimed_at"))}
    elif kind == "backup":
        body = export_backup()
    else:
        return HttpResponse(status=404)
    response = JsonResponse(body, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = f'attachment; filename="ai-radar-{kind}-{timezone.localdate()}.json"'
    return response


@private
@require_POST
def restore_data(request):
    if request.POST.get("confirm") != "RESTORE" or "file" not in request.FILES:
        messages.error(request, "请选择备份文件并输入 RESTORE 确认替换现有记录。")
        return redirect("settings")
    try:
        count = restore_backup(read_json(request.FILES["file"]), replace=True)
        messages.success(request, f"恢复完成，共 {count} 条记录。")
    except (ValueError, DatabaseError, DeserializationError, FetchError, UnicodeError):
        messages.error(request, "恢复失败，原有记录已保留。请检查备份版本、字段及记录关联。")
    return redirect("settings")


@private
@require_GET
def models_page(request):
    focus = request.GET.get("metric", "coding")
    focus = focus if focus in Observation.Dimension.values else "coding"
    options = list(Observation.objects.order_by("model").values_list("model", flat=True).distinct())
    selected = [model for model in request.GET.getlist("model")[:4] if model in options]
    if not selected:
        selected = list(dict.fromkeys(Observation.objects.filter(dimension=focus).order_by("-observed_on", "model")
                                      .values_list("model", flat=True)[:70]))[:3]
    data = list(Observation.objects.filter(model__in=selected, dimension=focus).order_by("-observed_on", "-pk")[:500])
    comparisons = []
    for model in selected:
        rows = {}
        for item in data:
            if item.model == model:
                rows.setdefault((item.metric, item.trust), item)
        comparisons.append((model, list(rows.values())[:20]))
    return page(request, "radar/models.html", {
        "title": "模型能力对比", "active": "models", "options": options, "focus": focus, "dimensions": Observation.Dimension.choices,
        "selected": selected, "comparisons": comparisons, "observation_count": len(options),
    })


@private
@require_http_methods(["GET", "POST"])
def observation_edit(request, observation_id=None):
    observation = get_object_or_404(Observation, pk=observation_id) if observation_id else None
    form = ObservationForm(request.POST or None, instance=observation)
    if request.method == "POST":
        if request.POST.get("action") == "delete" and observation:
            observation.delete()
            messages.success(request, "已删除记录。")
            return redirect("models")
        if form.is_valid():
            item = form.save()
            messages.success(request, "指标已保存。")
            return redirect(reverse("models") + "?" + urlencode({"model": item.model, "metric": item.dimension}))
    return page(request, "radar/form.html", {
        "title": "编辑模型指标" if observation else "添加模型指标", "active": "models",
        "form": form, "back_name": "models", "delete": bool(observation),
    })
