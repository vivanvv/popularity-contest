from __future__ import annotations

import csv
import datetime as dt
import http.client
import json
import pathlib
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .domains import normalize_domain


API_BASE = "https://tranco-list.eu/api/lists/date"
MISSING_RANK = 1_000_001
USER_AGENT = "popularity-contest/0.1 (+https://tranco-list.eu/)"


@dataclass(frozen=True)
class Snapshot:
    requested_date: str
    created_date: str
    list_id: str
    ranks: dict[str, int]


def normalize_date(value: str) -> str:
    if value == "latest":
        return value
    compact = value.replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ValueError("dates must be YYYY-MM-DD, YYYYMMDD, or latest")
    return compact


def weekly_dates(weeks: int, end_date: Optional[dt.date] = None) -> list[str]:
    end_date = end_date or dt.date.today()
    dates = [end_date - dt.timedelta(days=7 * offset) for offset in reversed(range(weeks))]
    return [date.strftime("%Y%m%d") for date in dates]


def request_text(url: str, retries: int = 3, prefer_curl: bool = False) -> str:
    if prefer_curl and shutil.which("curl"):
        return request_text_with_curl(url)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Optional[BaseException] = None

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return body.decode(charset)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if 400 <= exc.code < 500 and exc.code != 429:
                raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
        except (urllib.error.URLError, http.client.IncompleteRead, TimeoutError) as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(1.5 * attempt)

    if shutil.which("curl"):
        return request_text_with_curl(url)

    raise RuntimeError(f"Could not fetch {url} after {retries} attempts: {last_error}")


def request_text_with_curl(url: str) -> str:
    result = subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "5",
            "--retry-delay",
            "2",
            "--user-agent",
            USER_AGENT,
            url,
        ],
        check=False,
        capture_output=True,
        timeout=240,
    )
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl failed for {url}: {error}")
    return result.stdout.decode("utf-8", errors="replace")


def fetch_metadata(date_value: str) -> dict:
    metadata = json.loads(request_text(f"{API_BASE}/{date_value}"))
    if not metadata.get("available"):
        raise RuntimeError(f"Tranco list for {date_value} is unavailable: {metadata}")
    if "download" not in metadata:
        raise RuntimeError(f"Tranco response for {date_value} did not include a download URL")
    return metadata


def cache_path(cache_dir: pathlib.Path, metadata: dict) -> pathlib.Path:
    created = metadata.get("created_on", "")[:10] or "unknown-date"
    return cache_dir / f"{created}-{metadata['list_id']}-top-1m.csv"


def parse_ranks(text: str) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for row in csv.reader(text.splitlines()):
        if len(row) < 2:
            continue
        try:
            rank = int(row[0])
        except ValueError:
            continue
        domain = normalize_domain(row[1])
        if domain:
            ranks[domain] = rank
    return ranks


def load_snapshot(date_value: str, cache_dir: pathlib.Path) -> Snapshot:
    date_value = normalize_date(date_value)
    metadata = fetch_metadata(date_value)
    path = cache_path(cache_dir, metadata)

    if path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = request_text(metadata["download"], prefer_curl=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    return Snapshot(
        requested_date=date_value,
        created_date=str(metadata.get("created_on", ""))[:10],
        list_id=str(metadata["list_id"]),
        ranks=parse_ranks(text),
    )
