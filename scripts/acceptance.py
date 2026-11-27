"""Run once from the Altare app. Reports counts and outcomes without exposing credentials."""
import argparse
import http.cookiejar
import json
import os
import re
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from bs4 import BeautifulSoup

ORIGIN = "https://ai-radar.go.altare.global"
MARK = "AI Radar 线上验收 临时记录"
REAL_RSS = "https://blog.google/products/gemini/rss/"
BAD_RSS = "https://ai-radar-acceptance.invalid/feed"


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not newurl.startswith(ORIGIN + "/"):
            raise RuntimeError("Redirect outside the AI Radar origin.")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class Radar:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies), SameOriginRedirect())
        self.csrf = ""

    def request(self, path, data=None, status=200):
        headers = {"User-Agent": "AI-Radar production acceptance"}
        if data is not None:
            headers.update({"Origin": ORIGIN, "Referer": ORIGIN + path})
        encoded = urlencode({**data, "csrfmiddlewaretoken": self.csrf}).encode() if data is not None else None
        try:
            result = self.opener.open(Request(ORIGIN + path, encoded, headers), timeout=20)
        except HTTPError as error:
            result = error
        with result:
            if result.status != status:
                raise RuntimeError(f"{path.split('?')[0]} responded HTTP {result.status} (expected {status}).")
            payload = result.read()
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', payload)
        if token:
            self.csrf = token[1].decode()
        return payload

    def login(self):
        self.request("/api/feed/", status=401)
        self.request("/login/")
        assert self.csrf
        self.request("/login/", {"password": os.environ["ADMIN_PASSWORD"]})
        assert any(cookie.name == "__Host-radar" and cookie.secure for cookie in self.cookies)
        return self.json("/api/status/")

    def json(self, path):
        return json.loads(self.request(path))

    def records(self, label):
        return {row["pk"]: row["fields"] for row in self.json("/settings/export/backup/")["records"]
                if row["model"] == f"radar.{label}"}

    def add_source(self, name, url):
        self.request("/sources/new/", {"url": url, "name": name, "kind": "rss", "trust": "community",
                                      "weight": 50, "interval": 15, "enabled": "on"})
        return next(key for key, row in self.records("source").items() if row["url"] == url)

    def delete_source(self, key, name):
        if self.records("source").get(key, {}).get("name") == name:
            self.request(f"/sources/{key}/action/", {"action": "delete", "confirm": "delete"})


def before(radar, marker):
    base = radar.json("/api/feed/")
    assert base["filters"]["days"] == 3 and base["count"] > 0
    assert all(any(source["url"].startswith("https://") for source in item["sources"]) for item in base["items"])
    search = radar.json("/api/feed/?" + urlencode({"q": base["items"][0]["title"].split()[0]}))
    assert search["count"] > 0
    model = BeautifulSoup(radar.request("/models/"), "html.parser")
    assert model.select_one(".metric-item"), "The independent benchmark view is empty."
    for path in ("/sources/", "/status/", "/settings/", "/manifest.webmanifest", "/sw.js"):
        radar.request(path)
    form = radar.request("/sources/test/", {"url": REAL_RSS, "kind": "auto"})
    assert BeautifulSoup(form, "html.parser").select_one(".link-list li"), "RSS source test did not parse any article."
    events = radar.records("event")
    chosen = next((key for key, item in events.items() if item["category"] in {"offer", "cloud"} and item["claim"] == "open"
                   and not item["bookmarked"] and not item["claim_note"]), None)
    if marker.exists():
        raise RuntimeError("Acceptance marker already exists. Run the finish phase first.")
    with marker.open("x", encoding="utf-8") as file:
        json.dump({"source": None, "failure": None, "event": chosen}, file)
    try:
        good_url = REAL_RSS + "?" + urlencode({"radar_acceptance": uuid.uuid4().hex[:12]})
        good = radar.add_source(MARK, good_url)
        marker.write_text(json.dumps({"source": good, "failure": None, "event": chosen}), encoding="utf-8")
        failure = radar.add_source(MARK + " DNS", BAD_RSS)
        marker.write_text(json.dumps({"source": good, "failure": failure, "event": chosen}), encoding="utf-8")
        if chosen:
            radar.request(f"/event/{chosen}/update/", {"action": "bookmarked"})
            radar.request(f"/event/{chosen}/update/", {"action": "claim", "claim": "claimed", "claim_note": MARK})
            event = radar.records("event")[chosen]
            assert event["claim"] == "claimed" and event["bookmarked"] and event["claim_note"] == MARK
        print(json.dumps({"pre_restart": "passed", "recent_events": base["count"], "history": len(events),
                          "rss_source_added": bool(good), "failure_source_added": bool(failure),
                          "claim_and_favorite": bool(chosen)}, ensure_ascii=False))
    except Exception:
        finish(radar, marker, verify=False)
        raise


def finish(radar, marker, verify=True):
    tracks = json.loads(marker.read_text(encoding="utf-8"))
    sources = radar.records("source")
    event_id = tracks["event"]
    item = radar.records("event").get(event_id)
    good = sources.get(tracks["source"], {})
    failed = sources.get(tracks["failure"], {})
    result = {
        "source_survived": good.get("name") == MARK,
        "rss_success": bool(good.get("last_success")),
        "failure_recorded": bool(failed.get("streak") and failed.get("error")),
        "favorite_and_claim_survived": bool(item and item["bookmarked"] and item["claim"] == "claimed" and item["claim_note"] == MARK),
    }
    if verify and not all(result.values()):
        print(json.dumps({"post_restart": "pending", **result}))
        return
    if item and item["claim_note"] == MARK:
        radar.request(f"/event/{event_id}/update/", {"action": "claim", "claim": "open", "claim_note": ""})
        if item["bookmarked"]:
            radar.request(f"/event/{event_id}/update/", {"action": "bookmarked"})
    radar.delete_source(tracks["source"], MARK)
    radar.delete_source(tracks["failure"], MARK + " DNS")
    marker.unlink()
    if verify:
        print(json.dumps({"post_restart": "passed", **result, "test_only_records_removed": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "finish", "cleanup"])
    args = parser.parse_args()
    radar = Radar()
    state = radar.login()
    print("Private HTTPS login and authenticated API passed.")
    print(json.dumps(state, ensure_ascii=False))
    directory = Path(os.environ["RADAR_SQLITE_PATH"]).parent
    marker = directory / "acceptance-marker.json"
    if args.phase == "prepare":
        before(radar, marker)
    else:
        finish(radar, marker, verify=args.phase == "finish")
