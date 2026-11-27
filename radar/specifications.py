import re
from datetime import timedelta

from bs4 import BeautifulSoup
from django.db import transaction
from django.utils import timezone

from .models import Observation, Runtime, Source
from .network import FetchError, safe_get

Dimension = Observation.Dimension
DEEPSEEK = "https://api-docs.deepseek.com/quick_start/pricing/"
CLAUDE_DOC = "https://platform.claude.com/docs/en/models/overview"
CLAUDE = CLAUDE_DOC + ".md"


def deepseek_rows(body):
    soup = BeautifulSoup(body, "html.parser")
    table = soup.select_one("main table") or soup.select_one("article table")
    if not table:
        return []
    rows = [[(cell.get_text(" ", strip=True), cell.get("colspan", "1")) for cell in tr.find_all(["th", "td"], recursive=False)]
            for tr in table.select("tr")]
    models = next(([value for value, _ in row[1:]] for row in rows
                   if row and row[0][0].upper() == "MODEL VERSION"), [])
    if not models or len(models) > 8 or not all(re.fullmatch(r"DeepSeek-[\w.-]+", name, re.I) for name in models):
        return []
    fields = {
        "context length": (Dimension.CONTEXT, "API 上下文窗口", "DeepSeek 官方 API 的上下文长度。"),
        "max output": (Dimension.LIMITS, "API 最大输出", "DeepSeek 官方 API 单次请求最大输出长度。"),
        "vision": (Dimension.MEDIA, "视觉输入", "DeepSeek 文档针对该 API 版本的视觉输入支持。"),
        "concurrency limit (3)": (Dimension.LIMITS, "API 并发上限", "来源表中的并发限制，详细适用条件见官方脚注。"),
    }
    result = []
    price_type = ""
    for row in rows:
        if not row:
            continue
        key = row[0][0].casefold()
        if key in fields:
            dimension, metric, method = fields[key]
            values = [value for value, span in row[1:]]
            if len(values) == 1 and row[1][1] == str(len(models)):
                values *= len(models)
            if len(values) == len(models):
                result.extend((model, dimension, metric, value, "", method) for model, value in zip(models, values))
        context = next((value for value, span in row if value.upper() in {
            "1M INPUT TOKENS (CACHE HIT)", "1M INPUT TOKENS (CACHE MISS)", "1M OUTPUT TOKENS",
        }), "")
        period = next((value.upper() for value, span in row if value.upper() in {"PEAK", "OFF-PEAK"}), "")
        if context:
            price_type = {"1M INPUT TOKENS (CACHE HIT)": "输入，缓存命中",
                          "1M INPUT TOKENS (CACHE MISS)": "输入，缓存未命中",
                          "1M OUTPUT TOKENS": "输出"}[context]
        values = [value.removeprefix("$") for value, span in row if re.fullmatch(r"\$\d+(?:\.\d+)?", value)]
        if price_type and period and len(values) == len(models):
            metric = f"{price_type} · {'高峰' if period == 'PEAK' else '非高峰'}"
            result.extend((model, Dimension.COST, metric, price, "USD / 百万 tokens", "DeepSeek 官方美元价格，时段、脚注见原文。")
                          for model, price in zip(models, values))
    return result


def claude_rows(body):
    text = body.decode("utf-8")
    current = re.search(r"^## Latest models\s*\n([\s\S]+?)(?=^##\s|\Z)", text, re.M)
    if not current:
        return []
    table = [line.strip().strip("|").split("|") for line in current[1].splitlines() if line.startswith("|")]
    if not table:
        return []
    models = [name.strip() for name in table[0][1:]]
    if not 1 <= len(models) <= 8 or not all(re.fullmatch(r"Claude [A-Za-z]+ [0-9.]+", name) for name in models):
        return []
    result = []
    for row in table[1:]:
        if len(row) != len(models) + 1:
            continue
        label = row[0].strip().lower()
        values = [value.strip() for value in row[1:]]
        if label.startswith("[context window]") and all(re.fullmatch(r"\d+(?:\.\d+)?[KM]? tokens", value) for value in values):
            result.extend((model, Dimension.CONTEXT, "API 上下文窗口", value, "", "Anthropic 当前模型一览表中的 Claude API 上下文长度。")
                          for model, value in zip(models, values))
        elif label == "max output" and all(re.fullmatch(r"\d+(?:\.\d+)?[KM]? tokens", value) for value in values):
            result.extend((model, Dimension.LIMITS, "API 最大输出", value, "", "Anthropic 当前模型一览表中的最大输出长度。")
                          for model, value in zip(models, values))
        elif label.startswith("[pricing]") and all("$" in value and "MTok" in value for value in values):
            result.extend((model, Dimension.COST, "官方 API 定价", value, "", "Anthropic 公布的每百万输入及输出 tokens 美元起价或标价。")
                          for model, value in zip(models, values))
    return result


def refresh_specs(force=False):
    now = timezone.now()
    total = 0
    for name, url, reference, parser in [
        ("deepseek", DEEPSEEK, DEEPSEEK, deepseek_rows),
        ("claude", CLAUDE, CLAUDE_DOC, claude_rows),
    ]:
        attempt, success = f"{name}_spec_try", f"{name}_spec_ok"
        stamps = dict(Runtime.objects.filter(pk__in=[attempt, success]).values_list("pk", "at"))
        if not force and (stamps.get(attempt, now - timedelta(days=1)) > now - timedelta(minutes=60)
                          or stamps.get(success, now - timedelta(days=2)) > now - timedelta(hours=24)):
            continue
        Runtime.objects.update_or_create(pk=attempt, defaults={"at": now})
        try:
            rows = parser(safe_get(url).body)
        except (FetchError, ValueError):
            continue
        if not rows:
            continue
        with transaction.atomic():
            for model, dimension, metric, value, unit, method in rows:
                latest = Observation.objects.filter(model=model, dimension=dimension, metric=metric, url=reference,
                                                    trust=Source.Trust.OFFICIAL).order_by("-observed_on", "-pk").first()
                if latest and (latest.value, latest.unit, latest.method) == (value, unit, method):
                    continue
                Observation.objects.update_or_create(
                    model=model, dimension=dimension, metric=metric, url=reference, observed_on=timezone.localdate(),
                    defaults={"value": value, "unit": unit, "method": method, "trust": Source.Trust.OFFICIAL},
                )
                total += 1
            Runtime.objects.update_or_create(pk=success, defaults={"at": now})
    return total
