#!/usr/bin/env python3
"""
Find fast-rising domains by comparing two Tranco top-1M snapshots.

Examples:
  python3 tranco_growth.py --days-ago 90 --top 100
  python3 tranco_growth.py --old 2026-01-25 --new latest --output movers.csv
  python3 tranco_growth.py --domains domains.txt --days-ago 30
  python3 tranco_growth.py --old 20260125 --exclude-noise
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import http.client
import json
import math
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


API_BASE = "https://tranco-list.eu/api/lists/date"
MISSING_RANK_DEFAULT = 1_000_001
USER_AGENT = "tranco-growth/1.0 (+https://tranco-list.eu/)"

NOISE_SUFFIXES = (
    ".arpa",
    ".gvt1.com",
    ".googleusercontent.com",
    ".cloudfront.net",
    ".akamaihd.net",
    ".edgesuite.net",
    ".edgekey.net",
    ".azureedge.net",
    ".fastly.net",
    ".trafficmanager.net",
)

NOISE_TOKENS = (
    "cdn",
    "dns",
    "ns1",
    "ns2",
    "nameserver",
    "static",
    "assets",
    "tracking",
    "analytics",
    "telemetry",
    "metrics",
    "adserver",
    "adsystem",
)


def normalize_date(value: str) -> str:
    if value == "latest":
        return value
    compact = value.replace("-", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise argparse.ArgumentTypeError("date must be YYYYMMDD, YYYY-MM-DD, or latest")
    return compact


def date_days_ago(days: int) -> str:
    return (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d")


def request_text(url: str, retries: int = 3, prefer_curl: bool = False) -> str:
    if prefer_curl and shutil.which("curl"):
        return request_text_with_curl(url)

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: BaseException | None = None

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
    url = f"{API_BASE}/{date_value}"
    metadata = json.loads(request_text(url))
    if not metadata.get("available"):
        raise RuntimeError(f"Tranco list for {date_value} is not available: {metadata}")
    if "download" not in metadata:
        raise RuntimeError(f"Tranco response for {date_value} did not include a download URL")
    return metadata


def cache_path(cache_dir: pathlib.Path, metadata: dict) -> pathlib.Path:
    created = metadata.get("created_on", "")[:10] or "unknown-date"
    list_id = metadata["list_id"]
    return cache_dir / f"{created}-{list_id}-top-1m.csv"


def load_snapshot(date_value: str, cache_dir: pathlib.Path, use_cache: bool) -> tuple[dict[str, int], dict]:
    metadata = fetch_metadata(date_value)
    path = cache_path(cache_dir, metadata)

    if use_cache and path.exists():
        text = path.read_text(encoding="utf-8")
    else:
        text = request_text(metadata["download"], prefer_curl=True)
        if use_cache:
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

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

    return ranks, metadata


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value or value.startswith("#"):
        return ""

    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        value = parsed.netloc
    else:
        value = value.split("/", 1)[0]

    value = value.split("@")[-1]
    value = value.split(":", 1)[0]
    value = value.strip(".")

    if value.startswith("www."):
        value = value[4:]

    return value


def load_domain_filter(path: pathlib.Path) -> set[str]:
    domains: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        sample = file.read(4096)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if "," in sample else csv.excel
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(file, dialect)
        for row in reader:
            if not row:
                continue
            domain = normalize_domain(row[0])
            if domain and domain not in {"domain", "website", "url"}:
                domains.add(domain)
    return domains


def is_noisy_domain(domain: str) -> bool:
    if domain.endswith(NOISE_SUFFIXES):
        return True

    labels = domain.split(".")
    if len(labels) < 2:
        return True

    first_label = labels[0]
    if first_label in NOISE_TOKENS:
        return True

    return any(label in NOISE_TOKENS for label in labels[:-2])


def growth_score(old_rank: int, new_rank: int, missing_rank: int) -> float:
    rank_ratio = old_rank / new_rank
    top_weight = math.log10(max(2, missing_rank - new_rank))
    return math.log(rank_ratio) * top_weight


def build_rows(
    old_ranks: dict[str, int],
    new_ranks: dict[str, int],
    domains: set[str] | None,
    missing_rank: int,
    min_gain: int,
    min_ratio: float,
    max_new_rank: int,
    exclude_noise: bool,
    existing_only: bool,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    candidates = domains if domains is not None else set(new_ranks)

    for domain in candidates:
        new_rank = new_ranks.get(domain)
        if new_rank is None or new_rank > max_new_rank:
            continue

        if exclude_noise and is_noisy_domain(domain):
            continue

        old_rank = old_ranks.get(domain, missing_rank)
        if existing_only and old_rank == missing_rank:
            continue

        if old_rank <= new_rank:
            continue

        rank_gain = old_rank - new_rank
        rank_ratio = old_rank / new_rank
        if rank_gain < min_gain or rank_ratio < min_ratio:
            continue

        rows.append(
            {
                "domain": domain,
                "score": round(growth_score(old_rank, new_rank, missing_rank), 6),
                "old_rank": "" if old_rank == missing_rank else old_rank,
                "new_rank": new_rank,
                "rank_gain": rank_gain,
                "rank_ratio": round(rank_ratio, 4),
                "new_in_top_1m": old_rank == missing_rank,
            }
        )

    rows.sort(key=lambda row: (float(row["score"]), int(row["rank_gain"])), reverse=True)
    return rows


def write_csv(path: pathlib.Path, rows: list[dict[str, object]], old_meta: dict, new_meta: dict) -> None:
    fieldnames = [
        "domain",
        "score",
        "old_rank",
        "new_rank",
        "rank_gain",
        "rank_ratio",
        "new_in_top_1m",
        "old_list_id",
        "old_created_on",
        "new_list_id",
        "new_created_on",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            enriched = dict(row)
            enriched.update(
                {
                    "old_list_id": old_meta.get("list_id", ""),
                    "old_created_on": old_meta.get("created_on", ""),
                    "new_list_id": new_meta.get("list_id", ""),
                    "new_created_on": new_meta.get("created_on", ""),
                }
            )
            writer.writerow(enriched)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank fastest-rising websites by comparing two Tranco top-1M snapshots."
    )
    parser.add_argument("--old", type=normalize_date, help="Old Tranco date: YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--new", type=normalize_date, default="latest", help="New Tranco date or latest.")
    parser.add_argument(
        "--days-ago",
        type=int,
        default=90,
        help="Old snapshot offset if --old is omitted. Default: 90.",
    )
    parser.add_argument("--domains", type=pathlib.Path, help="Optional file of domains/URLs to score.")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("tranco-growth.csv"))
    parser.add_argument("--top", type=int, default=100, help="Number of rows to print to the terminal.")
    parser.add_argument("--max-new-rank", type=int, default=1_000_000)
    parser.add_argument("--min-gain", type=int, default=1_000)
    parser.add_argument("--min-ratio", type=float, default=1.2)
    parser.add_argument("--missing-rank", type=int, default=MISSING_RANK_DEFAULT)
    parser.add_argument("--cache-dir", type=pathlib.Path, default=pathlib.Path(".tranco-cache"))
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write cached Tranco CSVs.")
    parser.add_argument(
        "--exclude-noise",
        action="store_true",
        help="Skip obvious infrastructure, CDN, DNS, analytics, and ad-tech domains.",
    )
    parser.add_argument(
        "--existing-only",
        action="store_true",
        help="Only include domains that were already present in the old top-1M list.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    old_date = args.old or date_days_ago(args.days_ago)

    print(f"Loading old Tranco list: {old_date}", file=sys.stderr)
    old_ranks, old_meta = load_snapshot(old_date, args.cache_dir, not args.no_cache)

    print(f"Loading new Tranco list: {args.new}", file=sys.stderr)
    new_ranks, new_meta = load_snapshot(args.new, args.cache_dir, not args.no_cache)

    domains = load_domain_filter(args.domains) if args.domains else None
    if domains is not None:
        print(f"Scoring {len(domains):,} supplied domains", file=sys.stderr)
    else:
        print(f"Scoring {len(new_ranks):,} domains in the new Tranco list", file=sys.stderr)

    rows = build_rows(
        old_ranks=old_ranks,
        new_ranks=new_ranks,
        domains=domains,
        missing_rank=args.missing_rank,
        min_gain=args.min_gain,
        min_ratio=args.min_ratio,
        max_new_rank=args.max_new_rank,
        exclude_noise=args.exclude_noise,
        existing_only=args.existing_only,
    )

    write_csv(args.output, rows, old_meta, new_meta)

    print(f"Wrote {len(rows):,} rising domains to {args.output}", file=sys.stderr)
    print("domain,score,old_rank,new_rank,rank_gain,rank_ratio,new_in_top_1m")
    for row in rows[: args.top]:
        print(
            "{domain},{score},{old_rank},{new_rank},{rank_gain},{rank_ratio},{new_in_top_1m}".format(
                **row
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
