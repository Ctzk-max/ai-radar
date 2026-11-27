import os

from django.core.wsgi import get_wsgi_application
from django.conf import settings

from .ingress import protect_ingress

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "radar.settings")
application = get_wsgi_application()
if settings.PRODUCTION and settings.ORIGIN_HOST:
    application = protect_ingress(application)
