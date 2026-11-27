import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from .security import sensitive_query

USER_AGENT = "AI-Radar/1.0 (+https://github.com/Ctzk-max/ai-radar)"
TLS_CONTEXT = ssl.create_default_context()


class FetchError(Exception):
    def __init__(self, message, status="error", retry_seconds=0):
        super().__init__(message)
        self.status = status
        self.retry_seconds = retry_seconds


def public_ip(value):
    ip = ipaddress.ip_address(value)
    if ip.version == 6:
        return ip in ipaddress.ip_network("2000::/3") and ip.is_global and not (ip.sixtofour or ip.teredo)
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def public_url(value, *, source=False):
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f\\]", value) or len(value) > 1200:
        raise FetchError("URL 格式无效")
    try:
        url = urlsplit(value)
        host = (url.hostname or "").strip(".").lower()
        host = host.encode("idna").decode("ascii")
        port = url.port
        if url.scheme not in {"https", "http"} or not host or url.username is not None or url.password is not None:
            raise ValueError
        if port is not None and port != (443 if url.scheme == "https" else 80):
            raise ValueError
        if any(sensitive_query(key) for key, value in parse_qsl(url.query, max_num_fields=100)):
            raise FetchError("链接含可能泄露凭证的查询参数")
        if host in {"localhost", "metadata", "local"} or host.endswith((".local", ".localhost", ".internal", ".lan", ".home", ".onion")):
            raise FetchError("禁止本机、私有网络和云元数据地址")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z][a-z0-9-]{0,62})", host):
                raise ValueError from None
        else:
            if not public_ip(ip):
                raise FetchError("禁止本机、私有网络和云元数据地址")
            if source:
                raise FetchError("来源请使用公开域名")
            if ip.version == 6:
                host = f"[{host}]"
        path = quote(url.path or "/", safe="/:@!$&'()*+,;=-._~%")
        query = quote(url.query, safe="/?:@!$&'()*+,;=-._~%")
        normalized = urlunsplit((url.scheme, host, path, query, ""))
        if len(normalized) > 1200:
            raise ValueError
        return normalized
    except (ValueError, UnicodeError):
        raise FetchError("请输入公开 HTTP(S) URL，使用默认端口且无内嵌凭证") from None


def resolve_public(host, port):
    if os.getenv("RADAR_LOCAL_DOH") == "1" and os.getenv("RADAR_ENV") != "production" and os.getenv("ALTARE") != "1":
        addresses = local_doh(host, int(time.monotonic()) // 60)
    else:
        try:
            addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
        except OSError:
            raise FetchError("域名解析失败") from None
    if not addresses or any(not public_ip(addr) for addr in addresses):
        raise FetchError("域名解析到非公开地址")
    return sorted(addresses, key=lambda addr: ":" in addr)


@lru_cache(maxsize=256)
def local_doh(host, minute):
    """Local diagnostic resolver for Windows networks that synthesize benchmark-range DNS answers."""
    client = http.client.HTTPConnection("dns.google", timeout=4)
    try:
        with socket.create_connection(("8.8.8.8", 443), timeout=4) as raw:
            client.sock = TLS_CONTEXT.wrap_socket(raw, server_hostname="dns.google")
            client.request("GET", "/resolve?" + urlencode({"name": host, "type": "A"}))
            response = client.getresponse()
            if response.status != 200:
                raise OSError
            document = json.loads(response.read(65536))
            if document.get("Status") != 0:
                raise OSError
            return [item["data"] for item in document.get("Answer", []) if item.get("type") == 1]
    except (OSError, http.client.HTTPException, ValueError, KeyError):
        raise FetchError("本地 DNS 诊断解析失败") from None
    finally:
        client.close()


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes


def safe_get(value, *, conditional=None, max_bytes=4_000_000, timeout=16, accept=None):
    current = public_url(value, source=True)
    deadline = time.monotonic() + timeout
    original = current
    for _ in range(6):
        if time.monotonic() >= deadline:
            raise FetchError("来源连接超时")
        url = urlsplit(current)
        port = 443 if url.scheme == "https" else 80
        addresses = resolve_public(url.hostname, port)
        headers = {
            "User-Agent": USER_AGENT, "Connection": "close", "Accept-Encoding": "identity",
            "Accept": accept or "application/rss+xml, application/atom+xml, application/xml, text/html, */*;q=0.2",
        }
        if conditional and current == original:
            headers.update(conditional)
        target = urlunsplit(("", "", url.path, url.query, ""))
        connection = None
        watchdog = None
        try:
            for address in addresses[:3]:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError
                try:
                    raw = socket.create_connection((address, port), timeout=min(4, left))
                    break
                except OSError:
                    continue
            else:
                raise OSError
            def interrupt():
                try:
                    raw.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            watchdog = threading.Timer(max(0, deadline - time.monotonic()), interrupt)
            watchdog.daemon = True
            watchdog.start()
            connection = http.client.HTTPConnection(url.hostname, port, timeout=5)
            connection.sock = raw
            if url.scheme == "https":
                connection.sock = TLS_CONTEXT.wrap_socket(raw, server_hostname=url.hostname, do_handshake_on_connect=False)
                # TLS transfers ownership of the descriptor to SSLSocket.
                raw = connection.sock
                raw.do_handshake()
            connection.request("GET", target, headers=headers)
            result = connection.getresponse()
            try:
                response_headers = {key.lower(): value for key, value in result.getheaders()}
                if result.status in {301, 302, 303, 307, 308}:
                    location = response_headers.get("location")
                    if not location:
                        raise FetchError("来源返回无目标重定向")
                    next_url = public_url(urljoin(current, location), source=True)
                    if url.scheme == "https" and not next_url.startswith("https://"):
                        raise FetchError("禁止 HTTPS 降级跳转")
                    current = next_url
                    continue
                if result.status == 304:
                    return Response(current, 304, response_headers, b"")
                if result.status != 200:
                    retry = response_headers.get("retry-after", "")
                    raise FetchError(f"来源返回 HTTP {result.status}", retry_seconds=min(int(retry), 86400) if retry.isdigit() and len(retry) < 7 else 0)
                if response_headers.get("content-encoding", "identity").lower() != "identity":
                    raise FetchError("来源返回不支持的内容压缩")
                body = result.read(max_bytes + 1)
                if time.monotonic() >= deadline:
                    raise FetchError("来源响应超时")
                if len(body) > max_bytes:
                    raise FetchError("来源响应超过大小限制")
                return Response(current, 200, response_headers, body)
            finally:
                result.close()
        except (TimeoutError, socket.timeout):
            raise FetchError("来源连接或响应超时") from None
        except ssl.SSLError:
            raise FetchError("来源 TLS 证书或连接校验失败") from None
        except (OSError, http.client.HTTPException, UnicodeError):
            raise FetchError("来源网络连接失败") from None
        finally:
            if watchdog:
                watchdog.cancel()
            if connection:
                connection.close()
    raise FetchError("来源重定向次数过多")
