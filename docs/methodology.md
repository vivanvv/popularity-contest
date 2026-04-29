# Methodology

## Goal

Rank websites whose popularity appears to be increasing fastest.

This project optimizes for a cheap, reproducible popularity signal. It does not try to estimate exact visits or users.

## Source

The first source is Tranco top-1M snapshots.

Tranco is useful because it is free, historical, domain-level, and easy to download. Its limitation is that rank is not traffic. A domain moving from rank 100,000 to rank 20,000 is not guaranteed to have exactly five times the users.

## Core Improvement

Use a weekly time series instead of two snapshots.

A two-snapshot comparison answers:

```text
Did this domain rank better today than on one past date?
```

The better question is:

```text
Has this domain repeatedly improved from an older baseline into a strong recent rank?
```

## Ranking Modes

### Sustained Growth

Use this as the primary ranking.

Sustained growth finds domains that were already visible and have moved up consistently.

Default windows:

```text
history = 26 weekly snapshots
recent = last 4 weeks
baseline = weeks 13-26 before now
trend = last 12 weeks
```

Core metrics:

```text
recent_median_rank = median rank over the recent window
baseline_median_rank = median rank over the baseline window
growth_ratio = baseline_median_rank / recent_median_rank
log_growth = log10(baseline_median_rank) - log10(recent_median_rank)
improvement_rate = share of week-to-week comparisons that improved
presence_rate = share of historical snapshots where the domain appeared
volatility = standard deviation of log-rank over the trend window
jump_dominance = share of total improvement explained by the single largest jump
```

Default gates:

```text
presence_rate >= 70%
recent_presence >= 3 of last 4 weeks
recent_median_rank <= 100,000
growth_ratio >= 1.2
exclude obvious infrastructure/randomized domains
```

Default score:

```text
score =
  100 * (
    0.50 * log_growth
  + 0.20 * trend_gain
  + 0.20 * improvement_rate
  + 0.10 * current_rank_weight
  - 0.15 * volatility
  - 0.15 * jump_dominance_penalty
  )
```

Why this works better:

- Median windows reduce one-day measurement artifacts.
- Presence gates remove many random long-tail jumps.
- Current-rank weighting favors domains that are now meaningfully popular.
- Volatility and jump-dominance penalties reduce one-off spikes.

### Breakouts

Use this as a separate editorial queue.

Breakouts find domains that were absent or weak historically, then recently became visible.

Default gates:

```text
recent_presence >= 3 of last 4 weeks
recent_median_rank <= 100,000
baseline presence is sparse, or baseline rank was worse than 500,000
```

Breakouts are noisier than sustained growers. They should be reviewed manually or validated with another source before being presented as a polished ranking.

## Filtering

The default filter excludes domains that are likely to be measurement noise rather than consumer destinations:

- CDN, DNS, static asset, analytics, and ad-tech labels.
- Known infrastructure suffixes.
- Invalid domains.
- Randomized-looking labels.

Some domains are flagged but not excluded automatically:

- Adult or gambling-like tokens.
- Piracy/media mirror-like tokens.

Those are editorial-scope decisions, not purely methodology decisions.

## Validation Roadmap

The cheap ranking can stand on Tranco alone if the product claim is "popularity signals."

For higher confidence:

1. Add CrUX confirmation for real browser/user presence.
2. Add Cloudflare Radar for freshness and independent rank/trend context.
3. Use Similarweb/Semrush only for a paid final shortlist where exact traffic estimates matter.

## Output Columns

```text
domain
score
mode
recent_median_rank
baseline_median_rank
growth_ratio
log_growth
trend_gain
improvement_rate
presence_rate
recent_presence
volatility
jump_dominance
current_rank
flags
```

