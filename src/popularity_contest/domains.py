from __future__ import annotations

import csv
import pathlib
import urllib.parse


INFRASTRUCTURE_SUFFIXES = (
    ".arpa",
    ".cloudfront.net",
    ".akamaihd.net",
    ".edgesuite.net",
    ".edgekey.net",
    ".azureedge.net",
    ".fastly.net",
    ".trafficmanager.net",
    ".googleusercontent.com",
    ".gvt1.com",
)

INFRASTRUCTURE_LABELS = {
    "cdn",
    "dns",
    "ns",
    "ns1",
    "ns2",
    "static",
    "assets",
    "tracking",
    "analytics",
    "telemetry",
    "metrics",
    "adserver",
    "adsystem",
}

EDITORIAL_REVIEW_TOKENS = {
    "porn",
    "xxx",
    "sex",
    "casino",
    "bet",
    "bets",
    "betting",
    "wager",
    "movie",
    "movies",
    "filmy",
    "torrent",
}


def normalize_domain(value: str) -> str:
    value = value.strip().lower()
    if not value or value.startswith("#"):
        return ""

    if "://" in value:
        value = urllib.parse.urlparse(value).netloc
    else:
        value = value.split("/", 1)[0]

    value = value.split("@")[-1]
    value = value.split(":", 1)[0]
    value = value.strip(".")

    if value.startswith("www."):
        value = value[4:]

    return value


def load_domains(path: pathlib.Path) -> set[str]:
    domains: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        sample = file.read(4096)
        file.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample) if "," in sample else csv.excel
        except csv.Error:
            dialect = csv.excel

        for row in csv.reader(file, dialect):
            if not row:
                continue
            domain = normalize_domain(row[0])
            if domain and domain not in {"domain", "url", "website"}:
                domains.add(domain)

    return domains


def domain_flags(domain: str) -> list[str]:
    flags: list[str] = []
    labels = domain.split(".")

    if len(labels) < 2:
        return ["invalid_domain"]

    if domain.endswith(INFRASTRUCTURE_SUFFIXES):
        flags.append("infrastructure_suffix")

    if labels[0] in INFRASTRUCTURE_LABELS:
        flags.append("infrastructure_label")

    if any(label in INFRASTRUCTURE_LABELS for label in labels[:-2]):
        flags.append("infrastructure_subdomain")

    joined = " ".join(labels)
    if any(token in joined for token in EDITORIAL_REVIEW_TOKENS):
        flags.append("editorial_review_token")

    first_label = labels[0]
    digit_count = sum(char.isdigit() for char in first_label)
    if len(first_label) >= 12 and digit_count >= 4:
        flags.append("randomized_label")

    return flags


def is_excluded_by_default(domain: str) -> bool:
    flags = set(domain_flags(domain))
    return bool(
        flags
        & {
            "invalid_domain",
            "infrastructure_suffix",
            "infrastructure_label",
            "infrastructure_subdomain",
            "randomized_label",
        }
    )

