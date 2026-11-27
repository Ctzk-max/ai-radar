import ipaddress
import logging
import os
from functools import lru_cache

from django.conf import settings

# Published Cloudflare ingress ranges. Keep trusted socket peers separate from HTTP headers.
CLOUDFLARE = """
173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18
108.162.192.0/18 190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17
162.158.0.0/15 104.16.0.0/13 104.24.0.0/14 172.64.0.0/13 131.0.72.0/22
2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32 2405:8100::/32
2a06:98c0::/29 2c0f:f248::/32
"""
log = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def networks(custom):
    return tuple(ipaddress.ip_network(value) for value in (CLOUDFLARE + " " + custom).split())


def protect_ingress(app):
    trusted = networks(os.getenv("RADAR_TRUSTED_PROXY_NETWORKS", ""))
    logged = set()

    def wrapped(environ, start_response):
        host = environ.get("HTTP_HOST", "").lower().split(":", 1)[0]
        path = environ.get("PATH_INFO", "")
        if not settings.ORIGIN_HOST:
            return app(environ, start_response)
        if path == "/health/":
            environ["HTTP_HOST"] = settings.PUBLIC_HOST
            return app(environ, start_response)
        try:
            address = ipaddress.ip_address(environ.get("REMOTE_ADDR", ""))
            address = getattr(address, "ipv4_mapped", None) or address
        except ValueError:
            address = None
        proxy = address is not None and any(address in network for network in trusted)
        ray = bool(environ.get("HTTP_CF_RAY"))
        if proxy and host in {settings.PUBLIC_HOST, settings.ORIGIN_HOST} and ray:
            environ["HTTP_HOST"] = settings.PUBLIC_HOST
            environ["wsgi.url_scheme"] = "https"
            return app(environ, start_response)
        if ray and address and len(logged) < 8:
            subnet = str(ipaddress.ip_network(f"{address}/{24 if address.version == 4 else 56}", strict=False))
            if subnet not in logged:
                logged.add(subnet)
                log.warning("rejected ingress peer_subnet=%s role=%s", subnet, "known-host" if host in {settings.PUBLIC_HOST, settings.ORIGIN_HOST} else "unknown-host")
        if environ.get("REQUEST_METHOD") in {"GET", "HEAD"}:
            start_response("308 Permanent Redirect", [
                ("Location", settings.PUBLIC_URL + "/"), ("Cache-Control", "no-store"), ("Content-Length", "0"),
            ])
        else:
            start_response("403 Forbidden", [("Cache-Control", "no-store"), ("Content-Length", "0")])
        return [b""]

    return wrapped
