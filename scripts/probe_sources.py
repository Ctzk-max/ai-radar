"""Use the production adapters against the candidate catalog, without saving content."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "radar.settings")
import django

django.setup()

from radar.adapters import collect_source
from radar.catalog import SOURCES
from radar.models import Source
from radar.network import FetchError


def probe(config):
    result = {key: str(config[key]) for key in ("name", "kind", "url")}
    try:
        batch = collect_source(Source(**config))
        dates = [item.published for item in batch.items if item.published]
        result.update(resolved=batch.url, parsed=len(batch.items), kind=str(batch.kind),
                      latest=max(dates).isoformat() if dates else None,
                      sample=[item.title for item in batch.items[:3]])
    except FetchError as error:
        result.update(error=str(error))
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(probe, SOURCES))
    output = json.dumps({"at": datetime.now(timezone.utc).isoformat(), "sources": results}, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
