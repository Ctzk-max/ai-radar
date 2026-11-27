import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import feedparser
from bs4 import BeautifulSoup

from .models import Source
from .network import FetchError, public_url, safe_get


@dataclass
class Item:
    title: str
    url: str
    summary: str = ""
    published: datetime | None = None
    snapshot: bool = False
    evidence: dict = field(default_factory=dict)
    version: str = ""
    links: tuple = ()


@dataclass
class Batch:
    kind: str
    url: str
    items: list[Item] = field(default_factory=list)
    fingerprints: list = field(default_factory=list)
    etag: str = ""
    modified: str = ""
    unchanged: bool = False


def clean(value, limit=1300):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def date_value(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def link(base, value):
    try:
        return public_url(urljoin(base, str(value or ""))) if value else ""
    except FetchError:
        return ""


def references(soup, base, limit=12):
    return tuple(dict.fromkeys(url for a in soup.find_all("a", href=True, limit=80)
                               if (url := link(base, a["href"]))))[:limit]


def parse_feed(response):
    xml = re.sub(br"<!\[CDATA\[.*?\]\]>|<!--.*?-->", b"", response.body, flags=re.S)
    if re.search(br"<!\s*(?:doctype|entity)", xml.replace(b"\0", b""), re.I):
        raise FetchError("拒绝包含文档类型声明或实体的 XML")
    document = feedparser.parse(response.body, response_headers={
        "content-type": response.headers.get("content-type", "application/xml"),
        "content-location": response.url,
    })
    if not document.version:
        raise FetchError("返回内容无法识别为 RSS 或 Atom")
    entries = []
    for e in document.entries[:65]:
        title = clean(BeautifulSoup(e.get("title", ""), "html.parser").get_text(" "), 260)
        url = link(response.url, e.get("link")) or link(response.url, e.get("id", "") if str(e.get("id", "")).startswith("http") else "")
        if not (title and url):
            continue
        parsed = e.get("published_parsed") or e.get("updated_parsed")
        try:
            published = datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else None
        except (TypeError, ValueError):
            published = None
        description = e.get("summary") or next((value.get("value", "") for value in e.get("content", [])), "")
        text = BeautifulSoup(description[:40_000], "html.parser")
        entries.append(Item(title, url, clean(text.get_text(" "), 4000), published, links=references(text, response.url)))
    return entries


def detect(source):
    parts = urlsplit(source.url)
    host = parts.hostname
    path = parts.path.strip("/").split("/")
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        if len(path) != 1 or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", path[0]) or path[0].lower() in {
            "home", "explore", "search", "settings", "messages", "notifications", "i", "intent",
        }:
            raise FetchError("请输入 X 公开账号主页", "unsupported")
        if not source.bridge_url:
            raise FetchError("此 X 账号没有可用且获授权的 RSS 镜像。可改订阅作者的公开博客。", "unsupported")
        return Source.Kind.X, source.bridge_url
    if source.kind == Source.Kind.X:
        raise FetchError("仅支持登记 X 公开账号主页", "unsupported")
    if source.kind == Source.Kind.GITHUB or source.kind == Source.Kind.AUTO and host == "github.com":
        if host != "github.com" or len(path) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in {".", ".."} for p in path[:2]):
            raise FetchError("请输入 GitHub 仓库地址", "unsupported")
        if len(path) > 2 and path[2:] not in [["releases"], ["releases.atom"]]:
            raise FetchError("GitHub 适配器接受仓库首页或 Releases 地址", "unsupported")
        repo = path[1].removesuffix(".git")
        return Source.Kind.GITHUB, f"https://github.com/{path[0]}/{repo}/releases.atom"
    if source.kind == Source.Kind.RSS or parts.path.endswith((".rss", ".atom", ".xml")):
        return Source.Kind.RSS, source.url
    return source.kind, source.url


def extract_web(response, source):
    if response.headers.get("content-type", "").split(";")[0].strip() == "text/markdown":
        value = response.body.decode("utf-8", errors="replace")
        if len(value.strip()) < 60:
            raise FetchError("Markdown 内容不足")
        title = re.search(r"^# (.+)$", value, re.M)
        # Reuse the snapshot text path without interpreting upstream HTML.
        from html import escape
        response = type(response)(response.url, response.status, response.headers,
                                  f"<main><h1>{escape(title[1] if title else source.name)}</h1><p>{escape(value)}</p></main>".encode())
    soup = BeautifulSoup(response.body, "html.parser")
    if source.kind == Source.Kind.AUTO:
        for candidate in soup.find_all("link", rel="alternate", href=True):
            if candidate.get("type") in {"application/rss+xml", "application/atom+xml"}:
                target = link(response.url, candidate["href"])
                if target and target != response.url:
                    feed = safe_get(target)
                    return Batch(Source.Kind.RSS, feed.url, parse_feed(feed), etag=feed.headers.get("etag", ""),
                                 modified=feed.headers.get("last-modified", ""))
    for tag in soup.select("script, style, noscript, nav, footer, header, aside, form, [aria-hidden=true], iframe"):
        tag.decompose()
    if urlsplit(response.url).hostname == "api-docs.deepseek.com" and "/updates/" in response.url:
        releases = []
        for heading in soup.select("article h2[id]", limit=50):
            stamp = re.search(r"20\d{2}-\d{2}-\d{2}", heading.get_text())
            title = heading.find_next_sibling()
            if not stamp or not title or title.name != "h3" or not title.get("id"):
                continue
            content = []
            for node in title.find_next_siblings():
                if node.name in {"h2", "h3"}:
                    break
                content.append(node.get_text(" ", strip=True))
            from urllib.parse import urlencode
            url = link(response.url, "?" + urlencode({"release": title["id"]}))
            if url:
                releases.append(Item(clean(title.get_text(" ").replace("\u200b", ""), 260), url,
                                     clean(" ".join(content), 5000), date_value(stamp[0])))
        if releases:
            return Batch(Source.Kind.WEB, response.url, releases)
    if not source.selector:
        result = []
        for article in soup.select("article", limit=70):
            headline = article.select_one("h1, h2, h3, h4")
            anchor = headline.select_one("a[href]") if headline else None
            anchor = anchor or (headline.find_parent("a", href=True) if headline else None) or article.select_one("a[href]")
            time_tag = article.select_one("time[datetime]")
            if headline and anchor and (url := link(response.url, anchor["href"])):
                result.append(Item(clean(headline.get_text(" "), 260), url, clean(article.get_text(" "), 1500),
                                   date_value(time_tag.get("datetime")) if time_tag else None,
                                   links=references(article, response.url)))
        if len(result) > 1:
            return Batch(Source.Kind.WEB, response.url, result)
    try:
        section = soup.select_one(source.selector or "main, [role=main], article") or (soup.body if not source.selector else None)
    except (ValueError, NotImplementedError):
        raise FetchError("网页内容选择器无效") from None
    if section is None:
        raise FetchError("未找到网页内容区域")
    heading = section.find(["h1", "h2"]) or soup.title
    title = source.page_title or (clean(heading.get_text(" "), 260) if heading else source.name)
    text = clean(section.get_text(" "), 120_000)
    if len(text) < 60 or re.search(r"^(just a moment|access denied|verify (?:that )?you are human|attention required)", title, re.I):
        raise FetchError("页面内容不足或访问受限")
    candidates = re.split(r"[,，\n]+", source.keywords)
    matches = []
    for term in [i.strip() for i in candidates if i.strip()][:20]:
        for match in list(re.finditer(re.escape(term), text, re.I))[:3]:
            start = max(0, match.start() - 95)
            end = min(len(text), match.end() + 145)
            segment = text[start:end].strip()
            if segment and not any(segment in existing or existing in segment for existing in matches):
                matches.append(segment)
    relevant = " … ".join(matches)[:5800] if matches else text[:5800]
    fingerprint = hashlib.sha256(relevant.encode()).hexdigest()[:24]
    known = source.fingerprints or []
    if known and fingerprint == known[-1]:
        return Batch(Source.Kind.WEB, response.url, fingerprints=known)
    if known:
        title = f"{title} · 条款变更"
    return Batch(Source.Kind.WEB, response.url, [
        Item(title, response.url, relevant, snapshot=True, version=fingerprint, links=references(section, response.url)),
    ], [*known[-29:], fingerprint])


def collect_source(source):
    kind, target = detect(source)
    if source.fetch_url and source.detected_kind == Source.Kind.RSS and source.kind == Source.Kind.AUTO:
        kind, target = Source.Kind.RSS, source.fetch_url
    conditional = {}
    if source.fetch_url == target:
        if source.etag:
            conditional["If-None-Match"] = source.etag
        if source.last_modified:
            conditional["If-Modified-Since"] = source.last_modified
    response = safe_get(target, conditional=conditional)
    if response.status == 304:
        return Batch(kind, response.url, etag=source.etag, modified=source.last_modified, unchanged=True)
    must_feed = kind in {Source.Kind.GITHUB, Source.Kind.RSS, Source.Kind.X}
    content_type = response.headers.get("content-type", "")
    looks_feed = bool(re.search(br"<(?:[\w-]+:)?(?:rss|feed|rdf)(?=[\s>])", response.body[:4096], re.I))
    host = urlsplit(response.url).hostname
    if host == "huggingface.co" and urlsplit(response.url).path == "/api/models" and not must_feed:
        try:
            document = json.loads(response.body)
        except ValueError:
            raise FetchError("无法解析 Hugging Face 模型列表") from None
        if not isinstance(document, list):
            raise FetchError("Hugging Face 模型列表格式变化")
        items = []
        for row in document[:65]:
            if not isinstance(row, dict):
                continue
            identifier = row.get("id", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", identifier):
                continue
            items.append(Item(f"{identifier} · 模型发布", f"https://huggingface.co/{identifier}",
                              f"公开模型仓库。任务类型 {clean(row.get('pipeline_tag'), 120) or '未知'}，训练或推理详情见模型卡。",
                              date_value(row.get("createdAt"))))
        batch = Batch(Source.Kind.WEB, response.url, items)
    elif must_feed or looks_feed or "rss+xml" in content_type or "atom+xml" in content_type:
        batch = Batch(kind if must_feed else Source.Kind.RSS, response.url, parse_feed(response))
    else:
        batch = extract_web(response, source)
    if batch.url == response.url:
        batch.etag = response.headers.get("etag", "")[:300]
        batch.modified = response.headers.get("last-modified", "")[:140]
    return batch
