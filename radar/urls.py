from django.urls import path

from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("health/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("event/<int:event_id>/", views.event_detail, name="event"),
    path("event/<int:event_id>/update/", views.event_update, name="event-update"),
    path("models/", views.models_page, name="models"),
    path("models/observation/", views.observation_edit, name="observation"),
    path("models/observation/<int:observation_id>/", views.observation_edit, name="observation-edit"),
    path("sources/", views.sources, name="sources"),
    path("sources/new/", views.source_edit, name="source-new"),
    path("sources/<int:source_id>/edit/", views.source_edit, name="source-edit"),
    path("sources/<int:source_id>/action/", views.source_action, name="source-action"),
    path("sources/test/", views.source_test, name="source-test"),
    path("sources/import/", views.sources_import, name="sources-import"),
    path("status/", views.status_page, name="status"),
    path("settings/", views.preferences, name="settings"),
    path("settings/export/<str:kind>/", views.export_data, name="export"),
    path("settings/restore/", views.restore_data, name="restore"),
    path("api/feed/", views.api_feed, name="api-feed"),
    path("api/status/", views.api_status, name="api-status"),
]
