"""Check a running site through its HTTP entry point. Secrets are read from stdin or environment."""
import argparse
import getpass
import http.cookiejar
import json
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--performance", type=int, default=0)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    assert urlsplit(base).scheme == "https" or urlsplit(base).hostname in {"127.0.0.1", "localhost"}
    jar = http.cookiejar.CookieJar()
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(jar))

    def request(path, data=None):
        headers = {"User-Agent": "AI-Radar smoke test"}
        if data:
            headers.update({"Origin": base, "Referer": f"{base}/login/"})
        req = Request(base + path, data=urlencode(data).encode() if data else None, headers=headers)
        try:
            response = opener.open(req, timeout=12)
        except HTTPError as err:
            response = err
        with response:
            return response.status, response.headers, response.read()

    code, headers, body = request("/health/")
    assert code == 200 and json.loads(body)["status"] == "ok", f"health: HTTP {code}"
    print("Health", json.loads(body))
    result = request("/api/feed/")
    assert result[0] == 401, f"protected feed: HTTP {result[0]}"
    code, headers, body = request("/login/")
    assert code == 200 and b"csrfmiddlewaretoken" in body, f"login page: HTTP {code}"
    assert "no-store" in headers.get("Cache-Control", "")
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
    assert headers.get("Referrer-Policy") == "same-origin"
    if base.startswith("https://"):
        assert all(cookie.secure for cookie in jar), "authentication cookie must be Secure"
    if not args.private:
        print("Unauthenticated access is restricted. Login form and response headers passed.")
        return
    password = os.getenv("RADAR_SMOKE_PASSWORD") or getpass.getpass("AI Radar password: ")
    csrf = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body)
    assert csrf, "CSRF token missing from login form"
    code, _, _ = request("/login/", {"password": password, "csrfmiddlewaretoken": csrf[1].decode()})
    assert code == 200, f"login submission: HTTP {code}"
    status_code, _, status_bytes = request("/api/status/")
    feed_code, _, feed_bytes = request("/api/feed/")
    assert status_code == feed_code == 200, f"private API: HTTP {status_code}/{feed_code}"
    status = json.loads(status_bytes)
    feed = json.loads(feed_bytes)
    assert feed["filters"]["days"] == 3
    print("Feed", {"count": feed["count"], "days": feed["filters"]["days"]})
    print("Scheduler", status)
    for path in ("/models/", "/sources/", "/status/", "/settings/", "/manifest.webmanifest", "/sw.js"):
        assert request(path)[0] == 200, f"{path} unavailable"
    secure = [cookie.name for cookie in jar if cookie.secure]
    if base.startswith("https://"):
        assert "__Host-radar" in secure
    if args.performance:
        def timed(_):
            start = time.perf_counter()
            code, _, _ = request("/api/feed/?days=3")
            assert code == 200
            return (time.perf_counter() - start) * 1000
        size = min(200, max(10, args.performance))
        with ThreadPoolExecutor(max_workers=6) as pool:
            latencies = sorted(pool.map(timed, range(size)))
        print(f"Feed latency {size} requests / 6 clients: median={statistics.median(latencies):.1f}ms, "
              f"p95={latencies[int(size * .95) - 1]:.1f}ms, max={max(latencies):.1f}ms")


if __name__ == "__main__":
    main()
