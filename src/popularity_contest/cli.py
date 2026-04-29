from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Optional

from .domains import load_domains
from .export import print_rows, write_csv
from .scoring import ScoreConfig, breakouts, sustained_growth
from .tranco import load_snapshot, weekly_dates


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="popularity-contest",
        description="Rank domains by improving public popularity signals.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cache-dir", type=pathlib.Path, default=pathlib.Path("data/cache/tranco"))
    common.add_argument("--domains", type=pathlib.Path, help="Optional domain/URL watchlist to score.")
    common.add_argument("--weeks", type=int, default=26, help="Number of weekly Tranco snapshots to use.")
    common.add_argument("--top", type=int, default=100, help="Rows to print to stdout.")
    common.add_argument("--max-recent-rank", type=int, default=100_000)
    common.add_argument("--include-noise", action="store_true", help="Keep infrastructure/randomized domains.")

    subparsers = root.add_subparsers(dest="command", required=True)

    sustained = subparsers.add_parser("sustained", parents=[common], help="Rank steady popularity growers.")
    sustained.add_argument("--output", type=pathlib.Path, default=pathlib.Path("data/outputs/sustained.csv"))

    breakout = subparsers.add_parser("breakout", parents=[common], help="Rank newly emerging domains.")
    breakout.add_argument("--output", type=pathlib.Path, default=pathlib.Path("data/outputs/breakouts.csv"))

    all_modes = subparsers.add_parser("all", parents=[common], help="Generate sustained and breakout rankings.")
    all_modes.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path("data/outputs"))

    return root


def load_history(args: argparse.Namespace):
    date_values = weekly_dates(args.weeks)
    snapshots = []
    for index, date_value in enumerate(date_values, start=1):
        print(f"[{index}/{len(date_values)}] Loading Tranco snapshot {date_value}", file=sys.stderr)
        snapshots.append(load_snapshot(date_value, args.cache_dir))
    return snapshots


def score_config(args: argparse.Namespace) -> ScoreConfig:
    return ScoreConfig(
        max_recent_rank=args.max_recent_rank,
        exclude_noise=not args.include_noise,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    domains = load_domains(args.domains) if args.domains else None
    snapshots = load_history(args)
    config = score_config(args)

    if args.command == "sustained":
        rows = sustained_growth(snapshots, domains, config)
        write_csv(args.output, rows)
        print_rows(rows, args.top)
        print(f"Wrote {len(rows):,} rows to {args.output}", file=sys.stderr)
        return 0

    if args.command == "breakout":
        rows = breakouts(snapshots, domains, config)
        write_csv(args.output, rows)
        print_rows(rows, args.top)
        print(f"Wrote {len(rows):,} rows to {args.output}", file=sys.stderr)
        return 0

    sustained_rows = sustained_growth(snapshots, domains, config)
    breakout_rows = breakouts(snapshots, domains, config)
    write_csv(args.output_dir / "sustained.csv", sustained_rows)
    write_csv(args.output_dir / "breakouts.csv", breakout_rows)
    print_rows(sustained_rows, args.top)
    print(
        f"Wrote {len(sustained_rows):,} sustained rows and {len(breakout_rows):,} breakout rows to {args.output_dir}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
