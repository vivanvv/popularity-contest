from __future__ import annotations

import csv
import pathlib
import sys


FIELDNAMES = [
    "domain",
    "score",
    "mode",
    "recent_median_rank",
    "baseline_median_rank",
    "growth_ratio",
    "log_growth",
    "trend_gain",
    "improvement_rate",
    "presence_rate",
    "recent_presence",
    "volatility",
    "jump_dominance",
    "current_rank",
    "flags",
]


def write_csv(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def print_rows(rows: list[dict[str, object]], top: int) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows[:top])

