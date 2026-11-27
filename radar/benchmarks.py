import json
import math
import re
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import Observation, Runtime, Source
from .network import FetchError, safe_get

LEADERBOARD = "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json"
EXPERIMENTS = "https://github.com/swe-bench/experiments/tree/main/evaluation/verified/"


def extract_swe(document):
    if not isinstance(document, dict):
        raise FetchError("SWE-bench 返回了未知的榜单格式")
    verified = next((entry for entry in document.get("leaderboards", []) if entry.get("name") == "Verified"), None)
    if not verified or not isinstance(verified.get("results"), list):
        raise FetchError("SWE-bench Verified 榜单字段缺失")
    entries = []
    for result in verified["results"]:
        folder = result.get("folder", "")
        agent = result.get("agent", "")
        score = result.get("resolved")
        model = result.get("model_display") or result.get("name") or ""
        if result.get("warning") or agent.casefold() != "mini-swe-agent" or not re.fullmatch(r"[a-zA-Z0-9_.-]+", folder):
            continue
        if not 0 < len(model) <= 110 or not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 100:
            continue
        try:
            observed = date.fromisoformat(result.get("date", ""))
        except (TypeError, ValueError):
            continue
        harness = re.search(r"mini-v([0-9.]+)", folder, re.I)
        version = harness.group(1).strip(".") if harness else "未披露"
        review = "榜单标记主办方已核对" if result.get("checked") else "公开投稿，主办方核对状态未标记"
        method = f"500 道真实 GitHub 问题的解决率。mini-SWE-agent {version}，榜单记录 {result.get('name', model)}。{review}。"
        url = EXPERIMENTS + folder
        entries.append((model, f"{score:g}", method[:800], url, observed))
    if not entries:
        raise FetchError("榜单未返回可读取的可比记录")
    return entries


def update_benchmarks(force=False):
    stamps = dict(Runtime.objects.filter(pk__in=["benchmark_try", "benchmark_ok"]).values_list("pk", "at"))
    now = timezone.now()
    if not force:
        if stamps.get("benchmark_try") and stamps["benchmark_try"] > now - timedelta(minutes=30):
            return 0
        if stamps.get("benchmark_ok") and stamps["benchmark_ok"] > now - timedelta(hours=24):
            return 0
    Runtime.objects.update_or_create(pk="benchmark_try", defaults={"at": now})
    response = safe_get(LEADERBOARD, max_bytes=8_000_000, accept="application/json", timeout=25)
    try:
        rows = extract_swe(json.loads(response.body))
    except (ValueError, TypeError, AttributeError):
        raise FetchError("SWE-bench 返回了未知的榜单格式") from None
    with transaction.atomic():
        for model, value, method, url, observed in rows:
            Observation.objects.update_or_create(
                model=model, dimension=Observation.Dimension.CODING, metric="SWE-bench Verified（Bash Only）",
                url=url, observed_on=observed, defaults={
                    "value": value, "unit": "%", "method": method, "trust": Source.Trust.INDEPENDENT,
                },
            )
        Runtime.objects.update_or_create(pk="benchmark_ok", defaults={"at": now})
    return len(rows)
