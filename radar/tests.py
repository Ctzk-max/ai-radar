import json
from datetime import date, timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.serializers.json import DjangoJSONEncoder
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .adapters import Batch, Item, collect_source, parse_feed
from .backup import export_backup, restore_backup
from .benchmarks import extract_swe
from .collector import claim_source, collect_one
from .discovery import assess_candidates, enqueue_candidates
from .ingress import protect_ingress
from .intelligence import canonical, ingest
from .models import Category, Discovery, Event, EventReference, FetchRun, Observation, Preferences, Source
from .network import FetchError, Response, public_url, resolve_public
from .security import auth_version
from .specifications import claude_rows, deepseek_rows


class NetworkTests(SimpleTestCase):
    def test_private_and_encoded_addresses_are_blocked(self):
        for value in ("http://127.0.0.1", "http://2130706433", "http://0x7f.0.0.1", "http://169.254.169.254/latest",
                      "http://100.100.100.200", "https://[::1]", "https://[::ffff:127.0.0.1]",
                      "http://198.18.25.9", "https://user:pass@example.org/", "https://example.org:8443",
                      'https://example.org/?token=secret', 'https://example.org/?%61pi_key=secret', 'javascript:alert(1)',
                      "http://metadata.google.internal/", "https://example.com\\@127.0.0.1/"):
            with self.subTest(value=value), self.assertRaises(FetchError):
                public_url(value, source=True)

    def test_mixed_dns_is_rejected(self):
        with patch("radar.network.socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("10.0.0.1", 443)),
        ]), patch.dict("os.environ", {"RADAR_LOCAL_DOH": "0"}):
            with self.assertRaisesMessage(FetchError, "域名解析到非公开地址"):
                resolve_public("example.org", 443)

    def test_rss_atom_safe_and_declared_xml_rejected(self):
        url = "https://example.org/feed"
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>feed</title><entry>
        <title>Model published</title><link href="/new"/><updated>2026-11-20T10:00:00Z</updated>
        <summary type="html">&lt;b&gt;text&lt;/b&gt;</summary></entry></feed>"""
        items = parse_feed(Response(url, 200, {"content-type": "application/atom+xml"}, atom))
        self.assertEqual((items[0].url, items[0].summary), ("https://example.org/new", "text"))
        rss = b"""<rss version="2.0"><channel><title>site</title><item><title>news</title>
        <link>https://example.org/story</link><description><![CDATA[<!DOCTYPE html><b>body</b>]]></description>
        </item></channel></rss>"""
        self.assertEqual(parse_feed(Response(url, 200, {}, rss))[0].summary, "body")
        with self.assertRaises(FetchError):
            parse_feed(Response(url, 200, {}, b'<!DOCTYPE rss SYSTEM "file:///private"><rss/>'))

    def test_unsupported_x_does_not_fetch(self):
        with patch("radar.adapters.safe_get") as fetch, self.assertRaises(FetchError) as raised:
            collect_source(Source(name="account", url="https://x.com/example"))
        self.assertEqual(raised.exception.status, "unsupported")
        fetch.assert_not_called()

    def test_canonical_removes_tracking_but_preserves_distinct_releases(self):
        self.assertEqual(canonical("https://example.org/path/?utm_source=test&release=new#section"),
                         "https://example.org/path?release=new")

    def test_benchmark_preserves_harness_and_checked_status(self):
        data = {"leaderboards": [{"name": "Verified", "results": [
            {"agent": "mini-SWE-agent", "resolved": 72.8, "name": "Sample model (high)", "model_display": "Sample model",
             "folder": "20260217_mini-v2.1.0_sample", "date": "2026-02-17", "checked": True},
            {"agent": "Other", "resolved": 90, "folder": "other", "date": "2026-02-17"},
        ]}]}
        rows = extract_swe(data)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][1], rows[0][4]), ("72.8", date(2026, 2, 17)))
        self.assertIn("2.1.0", rows[0][2])

    @override_settings(ORIGIN_HOST="altare-origin.example.org", PUBLIC_HOST="radar.example.org",
                       PUBLIC_URL="https://radar.example.org")
    def test_ingress_requires_network_and_marks_only_edge_as_https(self):
        def app(values, reply):
            self.assertEqual(values["HTTP_HOST"], "radar.example.org")
            self.assertEqual(values["wsgi.url_scheme"], "https")
            reply("200 OK", [])
            return [b"ok"]
        wrapped = protect_ingress(app)
        values = {"HTTP_HOST": "altare-origin.example.org:1234", "PATH_INFO": "/login/",
                  "wsgi.url_scheme": "http", "HTTP_CF_RAY": "test", "HTTP_X_FORWARDED_PROTO": "https"}
        for addr, method, code in [("1.1.1.1", "POST", "403"), ("1.1.1.1", "GET", "308"), ("173.245.50.0", "GET", "200")]:
            statuses = []
            wrapped({**values, "REMOTE_ADDR": addr, "REQUEST_METHOD": method}, lambda status, headers: statuses.append(status))
            self.assertTrue(statuses[0].startswith(code))

    def test_model_specs_keep_units_and_billing_conditions(self):
        body = b"""<main><table><tr><th>MODEL VERSION</th><td>DeepSeek-V4.1-Flash</td><td>DeepSeek-V4-Pro</td></tr>
        <tr><th>CONTEXT LENGTH</th><td colspan="2">1M</td></tr>
        <tr><th>1M OUTPUT TOKENS</th><th>OFF-PEAK</th><td>$0.6</td><td>$1.98</td></tr>
        <tr><th>PEAK</th><td>$1.2</td><td>$3.96</td></tr></table></main>"""
        rows = deepseek_rows(body)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0][1:5], ("context", "API 上下文窗口", "1M", ""))
        self.assertEqual(rows[-1][1:5], ("cost", "输出 · 高峰", "3.96", "USD / 百万 tokens"))
        md = b"""## Latest models
| Feature | Claude Example 1.2 |
| [Context window](/docs) | 1M tokens |
| Max output | 128K tokens |
| [Pricing](/docs) | From $1 / input MTok, $2 / output MTok |
## Other
"""
        self.assertEqual([r[1] for r in claude_rows(md)], ["context", "limits", "cost"])


class CollectionTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(name="Official", url="https://openai.com/feed/", kind="rss",
                                            trust="official", platform="OpenAI", category=Category.OFFER)

    def item(self):
        cutoff = (timezone.now().replace(microsecond=0) + timedelta(days=9)).isoformat()
        return Item("ChatGPT introduces a free student plan", "https://openai.com/students?utm_medium=rss",
                    f"A free tier and student plan. Apply at the official page. Valid until {cutoff}.")

    def test_discovery_requires_recent_relevant_feed_items_and_review(self):
        now = timezone.now()
        sample = self.item()
        sample.published = now
        sample.links = ("https://new-source.example.org/path", "https://x.com/example", "https://127.0.0.1/rss")
        self.source.weight = 72
        enqueue_candidates(self.source, [sample], now)
        candidate = Discovery.objects.get()
        self.assertEqual(candidate.url, "https://new-source.example.org/")
        items = [sample, Item("Gemini offers free tier", "https://new-source.example.org/gemini", "New API free tier", now)]
        with patch("radar.discovery.collect_source", return_value=Batch("rss", candidate.url, items)):
            self.assertEqual(assess_candidates(), 1)
        candidate.refresh_from_db()
        self.assertEqual((candidate.status, candidate.items), ("ready", 2))
        self.assertFalse(Source.objects.filter(url=candidate.url).exists())

    def test_ingestion_merges_url_deduplicates_and_retains_provenance(self):
        self.assertEqual(ingest(self.source, [self.item()]), 1)
        other = Source.objects.create(name="Community", url="https://example.org/feed", kind="rss")
        self.assertEqual(ingest(other, [self.item()]), 0)
        self.assertEqual(ingest(other, [self.item()]), 0)
        event = Event.objects.get()
        self.assertTrue(event.first_party)
        self.assertEqual(event.eligibility()[0], "可以领取")
        self.assertEqual(EventReference.objects.count(), 2)

    def test_similar_event_deduplicates_but_versions_stay_distinct(self):
        source = Source.objects.create(name="Tool", url="https://example.org/", category=Category.TOOL)
        ingest(source, [
            Item("OpenCode 1.2.3 adds reliable coding agent support", "https://example.org/story1"),
            Item("OpenCode 1.2.3 adds reliable coding agent support today", "https://example.org/story2"),
            Item("OpenCode 1.2.4 adds reliable coding agent support", "https://example.org/story3"),
        ])
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(EventReference.objects.count(), 3)

    def test_unverified_offer_and_ad_filtered(self):
        fake = Item("ChatGPT offers free credits to users", "https://example.org/news", "A free tier, student plan.")
        ingest(self.source, [fake, Item("Sponsored post: free tier", "https://example.org/ad", "free tier")])
        event = Event.objects.get()
        self.assertFalse(event.first_party)
        self.assertEqual(event.eligibility()[0], "尚未核实")

    def test_retry_and_recovery_and_auditable_counts(self):
        with patch("radar.collector.collect_source", side_effect=FetchError("HTTP 429", retry_seconds=5000)):
            self.assertEqual(collect_one(self.source.pk, manual=True).status, "error")
        self.source.refresh_from_db()
        self.assertEqual(self.source.streak, 1)
        self.assertGreater(self.source.next_check - self.source.last_checked, timedelta(seconds=4900))
        self.assertEqual(collect_one(self.source.pk), None)
        with patch("radar.collector.collect_source", return_value=Batch("rss", self.source.url, [self.item()], etag='"1"')):
            self.assertEqual(collect_one(self.source.pk, manual=True).added, 1)
        self.source.refresh_from_db()
        self.assertEqual((self.source.streak, self.source.etag, self.source.error), (0, '"1"', ""))
        self.assertEqual(FetchRun.objects.count(), 2)

    def test_leases_expire_and_do_not_allow_overlap(self):
        self.assertIsNotNone(claim_source(self.source.pk))
        self.assertIsNone(claim_source(self.source.pk, manual=True))
        Source.objects.filter(pk=self.source.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        self.assertIsNotNone(claim_source(self.source.pk))


@override_settings(LEGACY_PASSWORD="disposable-test-password", ADMIN_PASSWORD_HASH="")
class WebTests(TestCase):
    def login(self, client=None):
        client = client or self.client
        session = client.session
        session["radar_admin"] = auth_version()
        session.save()
        return client

    def event(self, title="Provider free credits", **values):
        return Event.objects.create(title=title, normalized=title.casefold(), category=Category.OFFER,
                                    platform="Example", canonical_url="https://example.org/offer", **values)

    def test_private_routes_and_login_csrf_session_and_logout(self):
        client = Client(enforce_csrf_checks=True)
        self.assertRedirects(client.get("/"), "/login/")
        self.assertEqual(client.get("/api/feed/").status_code, 401)
        self.assertEqual(client.post("/login/", {"password": "disposable-test-password"}).status_code, 403)
        response = client.get("/login/")
        csrf = response.context["csrf_token"]
        old = client.session.session_key
        response = client.post("/login/", {"password": "disposable-test-password", "csrfmiddlewaretoken": csrf})
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(old, client.session.session_key)
        cookie = response.cookies["radar_dev"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        response = client.get("/")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("script-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        csrf = response.context["csrf_token"]
        self.assertEqual(client.post("/logout/", {"csrfmiddlewaretoken": csrf}).status_code, 302)
        self.assertEqual(client.get("/api/status/").status_code, 401)

    def test_login_throttle(self):
        with patch("radar.views.verify_password", return_value=False):
            for _ in range(12):
                self.assertEqual(self.client.post("/login/", {"password": "incorrect"}).status_code, 400)
            self.assertEqual(self.client.post("/login/", {"password": "incorrect"}).status_code, 429)

    def test_feed_search_filters_feedback_favorites_and_claim(self):
        self.login()
        new = self.event("Gamma free research credits", priority=50)
        lower = self.event("Alpha research free credits", priority=55)
        self.event("Legacy offer", published_at=timezone.now() - timedelta(days=8))
        result = self.client.get("/api/feed/", {"q": "research"}).json()
        self.assertEqual([item["id"] for item in result["items"]], [lower.pk, new.pk])
        Preferences.objects.filter(pk=1).update(interests="Gamma")
        self.assertEqual(self.client.get("/api/feed/").json()["items"][0]["id"], new.pk)
        for action in ("bookmarked", "read", "pinned", "hidden"):
            self.assertEqual(self.client.post(f"/event/{new.pk}/update/", {"action": action}).status_code, 302)
        self.client.post(f"/event/{new.pk}/update/", {"action": "claim", "claim": "claimed", "claim_note": "Verified locally"})
        new.refresh_from_db()
        self.assertEqual((new.bookmarked, new.read, new.pinned, new.hidden, new.claim), (True, True, True, True, "claimed"))
        self.assertIsNotNone(new.claimed_at)
        self.assertEqual(self.client.get("/api/feed/").json()["count"], 1)
        self.assertEqual(self.client.get("/api/feed/", {"section": "saved"}).json()["count"], 1)
        self.assertEqual(self.client.get("/api/feed/", {"section": "history"}).json()["count"], 3)

    def test_empty_and_xss_safe_templates(self):
        self.login()
        self.assertContains(self.client.get("/"), "没有匹配的情报")
        item = self.event("<script>alert(1)</script>")
        response = self.client.get(f"/event/{item.pk}/")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        for url in ("/sources/", "/status/", "/models/", "/settings/", "/manifest.webmanifest", "/health/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_sources_add_test_edit_pause_export_delete(self):
        self.login()
        data = {"url": "https://example.org/feed", "name": "Test", "kind": "auto", "trust": "community",
                "weight": 64, "interval": 15, "enabled": True}
        self.assertEqual(self.client.post("/sources/new/", {**data, "url": "http://127.0.0.1"}).status_code, 400)
        self.assertRedirects(self.client.post("/sources/new/", data), "/sources/")
        source = Source.objects.get()
        self.assertRedirects(self.client.post(f"/sources/{source.pk}/edit/", {**data, "name": "Updated"}), "/sources/")
        self.client.post(f"/sources/{source.pk}/action/", {"action": "toggle"})
        source.refresh_from_db()
        self.assertFalse(source.enabled)
        self.assertEqual(source.name, "Updated")
        result = self.client.get("/settings/export/sources/").json()
        self.assertEqual(result["sources"][0]["url"], source.url)
        with patch("radar.views.collect_source", return_value=Batch("rss", source.url, [Item("Title", source.url)])):
            self.assertContains(self.client.post("/sources/test/", {"url": source.url, "kind": "auto"}), "Title")
        self.assertEqual(self.client.post(f"/sources/{source.pk}/action/", {"action": "delete"}).status_code, 200)
        self.assertTrue(Source.objects.exists())
        self.assertRedirects(self.client.post(f"/sources/{source.pk}/action/", {"action": "delete", "confirm": "delete"}), "/sources/")
        self.assertFalse(Source.objects.exists())

    def test_source_import_is_atomic_and_ignores_duplicates(self):
        self.login()
        url = "https://example.org/rss"
        def upload(data):
            file = SimpleUploadedFile("sources.json", json.dumps(data).encode())
            return self.client.post("/sources/import/", {"file": file})
        upload([{"url": url}, {"url": "https://127.0.0.1/"}])
        self.assertFalse(Source.objects.exists())
        upload([{"url": url}, {"url": url}])
        self.assertEqual(Source.objects.count(), 1)

    def test_backup_restore_bookmark_claim_and_validation(self):
        self.login()
        initial = self.event(bookmarked=True, claim=Event.Claim.CLAIMED, claim_note="checked", claimed_at=timezone.now())
        Source.objects.create(name="Test", url="https://example.org/rss/")
        document = json.loads(json.dumps(export_backup(), cls=DjangoJSONEncoder))
        initial.delete()
        self.assertGreater(restore_backup(document, replace=True), 1)
        self.assertEqual(Event.objects.get().claim_note, "checked")
        invalid = json.loads(json.dumps(document))
        next(row for row in invalid["records"] if row["model"] == "radar.event")["fields"]["canonical_url"] = "javascript:alert(1)"
        with self.assertRaises(FetchError):
            restore_backup(invalid, replace=True)
        self.assertTrue(Event.objects.get().bookmarked)
        self.assertEqual(len(self.client.get("/settings/export/bookmarks/").json()["events"]), 1)

    def test_model_comparison_records_metadata_and_missing_dimensions(self):
        self.login()
        row = Observation.objects.create(model="Model 1.0", dimension="coding", metric="Benchmark", method="500 tasks",
                                         value="70.4", unit="%", observed_on=date(2026, 10, 1), trust="independent",
                                         url="https://example.org/bench")
        response = self.client.get("/models/", {"model": row.model, "metric": "coding"})
        for text in ("Model 1.0", "70.4", "500 tasks", "2026-10-01"):
            self.assertContains(response, text)
        self.assertContains(self.client.get("/models/", {"model": row.model, "metric": "writing"}), "暂无数据")
