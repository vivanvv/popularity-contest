from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Optional

from .domains import domain_flags, is_excluded_by_default
from .tranco import MISSING_RANK, Snapshot


@dataclass(frozen=True)
class ScoreConfig:
    recent_weeks: int = 4
    baseline_start_weeks_ago: int = 26
    baseline_end_weeks_ago: int = 13
    trend_weeks: int = 12
    max_recent_rank: int = 100_000
    min_growth_ratio: float = 1.2
    min_presence_rate: float = 0.70
    min_recent_presence: int = 3
    exclude_noise: bool = True


def median(values: Iterable[int]) -> float:
    return float(statistics.median(list(values)))


def log_rank(rank: float) -> float:
    return math.log10(max(1.0, rank))


def rank_series(snapshots: list[Snapshot], domains: Optional[set[str]] = None) -> dict[str, list[int]]:
    candidates = set(domains or [])
    if domains is None:
        for snapshot in snapshots:
            candidates.update(snapshot.ranks)

    return {
        domain: [snapshot.ranks.get(domain, MISSING_RANK) for snapshot in snapshots]
        for domain in candidates
    }


def presence_rate(ranks: list[int]) -> float:
    return sum(rank < MISSING_RANK for rank in ranks) / len(ranks)


def improvement_rate(ranks: list[int]) -> float:
    comparisons = 0
    improvements = 0
    for old_rank, new_rank in zip(ranks, ranks[1:]):
        if old_rank == MISSING_RANK or new_rank == MISSING_RANK:
            continue
        comparisons += 1
        if new_rank < old_rank:
            improvements += 1
    return improvements / comparisons if comparisons else 0.0


def trend_gain(ranks: list[int]) -> float:
    if len(ranks) < 4:
        return 0.0
    midpoint = len(ranks) // 2
    early = median(ranks[:midpoint])
    late = median(ranks[midpoint:])
    return max(0.0, log_rank(early) - log_rank(late))


def volatility(ranks: list[int]) -> float:
    values = [log_rank(rank) for rank in ranks if rank < MISSING_RANK]
    return statistics.pstdev(values) if len(values) > 1 else 1.0


def jump_dominance(ranks: list[int]) -> float:
    gains: list[float] = []
    for old_rank, new_rank in zip(ranks, ranks[1:]):
        if old_rank == MISSING_RANK or new_rank == MISSING_RANK or new_rank >= old_rank:
            continue
        gains.append(log_rank(old_rank) - log_rank(new_rank))

    total = sum(gains)
    return max(gains) / total if total > 0 else 0.0


def rank_weight(rank: float) -> float:
    return max(0.0, min(1.0, 1.0 - log_rank(rank) / log_rank(MISSING_RANK)))


def sustained_growth(snapshots: list[Snapshot], domains: Optional[set[str]], config: ScoreConfig) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sample_count = len(snapshots)
    baseline_start = max(0, sample_count - config.baseline_start_weeks_ago)
    baseline_end = max(baseline_start + 1, sample_count - config.baseline_end_weeks_ago)

    for domain, ranks in rank_series(snapshots, domains).items():
        flags = domain_flags(domain)
        if config.exclude_noise and is_excluded_by_default(domain):
            continue

        recent = ranks[-config.recent_weeks :]
        baseline = ranks[baseline_start:baseline_end]
        trend = ranks[-config.trend_weeks :]

        recent_median = median(recent)
        baseline_median = median(baseline)
        domain_presence_rate = presence_rate(ranks)
        recent_presence = sum(rank < MISSING_RANK for rank in recent)

        if domain_presence_rate < config.min_presence_rate:
            continue
        if recent_presence < config.min_recent_presence:
            continue
        if recent_median > config.max_recent_rank:
            continue
        if baseline_median <= recent_median:
            continue

        growth_ratio = baseline_median / recent_median
        if growth_ratio < config.min_growth_ratio:
            continue

        log_growth = log_rank(baseline_median) - log_rank(recent_median)
        consistency = improvement_rate(trend)
        trend_component = trend_gain(trend)
        volatility_value = volatility(trend)
        dominance = jump_dominance(trend)
        dominance_penalty = max(0.0, dominance - 0.65)

        score = 100 * (
            0.50 * log_growth
            + 0.20 * trend_component
            + 0.20 * consistency
            + 0.10 * rank_weight(recent_median)
            - 0.15 * volatility_value
            - 0.15 * dominance_penalty
        )

        rows.append(
            {
                "domain": domain,
                "score": round(score, 6),
                "mode": "sustained",
                "recent_median_rank": round(recent_median, 2),
                "baseline_median_rank": round(baseline_median, 2),
                "growth_ratio": round(growth_ratio, 4),
                "log_growth": round(log_growth, 6),
                "trend_gain": round(trend_component, 6),
                "improvement_rate": round(consistency, 4),
                "presence_rate": round(domain_presence_rate, 4),
                "recent_presence": recent_presence,
                "volatility": round(volatility_value, 6),
                "jump_dominance": round(dominance, 6),
                "current_rank": ranks[-1] if ranks[-1] < MISSING_RANK else "",
                "flags": "|".join(flags),
            }
        )

    rows.sort(key=lambda row: (float(row["score"]), -float(row["recent_median_rank"])), reverse=True)
    return rows


def breakouts(snapshots: list[Snapshot], domains: Optional[set[str]], config: ScoreConfig) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    baseline_weeks = max(1, len(snapshots) - config.recent_weeks)

    for domain, ranks in rank_series(snapshots, domains).items():
        flags = domain_flags(domain)
        if config.exclude_noise and is_excluded_by_default(domain):
            continue

        recent = ranks[-config.recent_weeks :]
        baseline = ranks[:baseline_weeks]
        recent_median = median(recent)
        baseline_median = median(baseline)
        recent_presence = sum(rank < MISSING_RANK for rank in recent)
        baseline_presence = presence_rate(baseline)

        if recent_presence < config.min_recent_presence:
            continue
        if recent_median > config.max_recent_rank:
            continue
        if baseline_presence > 0.20 and baseline_median < 500_000:
            continue

        emergence = 1.0 - baseline_presence
        consistency = improvement_rate(recent)
        score = 100 * (0.55 * rank_weight(recent_median) + 0.30 * emergence + 0.15 * consistency)

        rows.append(
            {
                "domain": domain,
                "score": round(score, 6),
                "mode": "breakout",
                "recent_median_rank": round(recent_median, 2),
                "baseline_median_rank": "" if baseline_median == MISSING_RANK else round(baseline_median, 2),
                "growth_ratio": "" if baseline_median == MISSING_RANK else round(baseline_median / recent_median, 4),
                "log_growth": "" if baseline_median == MISSING_RANK else round(log_rank(baseline_median) - log_rank(recent_median), 6),
                "trend_gain": round(trend_gain(recent), 6),
                "improvement_rate": round(consistency, 4),
                "presence_rate": "",
                "recent_presence": recent_presence,
                "volatility": round(volatility(recent), 6),
                "jump_dominance": round(jump_dominance(recent), 6),
                "current_rank": ranks[-1] if ranks[-1] < MISSING_RANK else "",
                "flags": "|".join(flags),
            }
        )

    rows.sort(key=lambda row: (float(row["score"]), -float(row["recent_median_rank"])), reverse=True)
    return rows
