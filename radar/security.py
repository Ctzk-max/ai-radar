import hashlib
import re
from functools import lru_cache, wraps

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.http import JsonResponse
from django.shortcuts import redirect


@lru_cache(maxsize=4)
def password_hash(configured, legacy):
    return configured or (make_password(legacy) if legacy else "")


def verify_password(password):
    encoded = password_hash(settings.ADMIN_PASSWORD_HASH, settings.LEGACY_PASSWORD)
    return bool(encoded and 0 < len(password) <= 256 and check_password(password, encoded))


def auth_version():
    credential = settings.ADMIN_PASSWORD_HASH or settings.LEGACY_PASSWORD
    return hashlib.sha256((settings.SECRET_KEY + "\0" + credential).encode()).hexdigest()


def authenticated(request):
    return request.session.get("radar_admin") == auth_version()


def private(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if authenticated(request):
            return view(request, *args, **kwargs)
        if request.path.startswith("/api/"):
            return JsonResponse({"error": "需要登录"}, status=401)
        return redirect("login")
    return wrapped


def private_headers(get_response):
    def middleware(request):
        response = get_response(request)
        response["Cache-Control"] = "private, no-store"
        response["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "manifest-src 'self'; connect-src 'self'; worker-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
    return middleware


def sensitive_query(name):
    return re.search(r"token|secret|pass(word)?|api[-_]?key|authorization|^auth$|^key$|signature|^sig$|"
                     r"credential|access[-_]?key|^session(id)?$|^code$", name, flags=re.I) is not None
