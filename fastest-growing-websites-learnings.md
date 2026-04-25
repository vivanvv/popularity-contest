# Fastest-Growing Websites: Task Notes and Learnings

## Goal

Build a cheap way to find websites whose popularity is increasing fastest.

The practical target is not exact traffic. Exact traffic for competitor sites requires paid datasets such as Similarweb or Semrush. The cheap target is:

- discover likely fast-growing domains,
- reduce obvious false positives,
- rank them by sustained popularity growth,
- validate the shortlist with stronger signals when needed.

## What Was Built

`tranco_growth.py` compares two Tranco top-1M snapshots and ranks domains that improved.

Example:

```bash
./tranco_growth.py --days-ago 90 --existing-only --exclude-noise --top 100 --output tranco-growth.csv
```

Useful options:

```bash
# Include domains that newly entered the top 1M.
./tranco_growth.py --days-ago 90 --exclude-noise --output tranco-growth-with-new.csv

# Use exact dates.
./tranco_growth.py --old 2026-01-25 --new latest --existing-only --exclude-noise

# Score only a supplied list of domains.
./tranco_growth.py --domains domains.txt --days-ago 90 --output my-domains-growth.csv
```

The script caches downloaded Tranco CSVs in `.tranco-cache`.

## What Went Wrong

The first metric was too brittle because it used a two-point comparison:

```text
rank 90 days ago -> rank today
```

That finds rank discontinuities, not necessarily real sustained growth.

Observed issues:

- It over-rewards long-tail jumps, for example domains moving from rank 900,000 to 10,000.
- It under-rewards important movement near the top, for example rank 180 to 33.
- It surfaces noisy domains: infrastructure, CDN, DNS, ad tech, spam, adult, gambling, mirrors, and random short-lived domains.
- Tranco rank is not traffic. It is a popularity ranking assembled from multiple signals.
- `--min-gain 1000` filtered out top-site growth because top domains can grow massively with small absolute rank changes.

Example from the cached comparison, `2026-01-25` to `2026-04-24`:

| Domain | Old Rank | New Rank | Rank Gain | Rank Ratio | Score |
|---|---:|---:|---:|---:|---:|
| `chatgpt.com` | 180 | 33 | 147 | 5.4545x | 10.178672 |
| `claude.com` | 13,328 | 4,564 | 8,764 | 2.9202x | 6.427877 |
| `claude.ai` | 2,673 | 991 | 1,682 | 2.6973x | 5.953026 |

`chatgpt.com` was excluded from the generated CSV when `--min-gain 1000` was used, despite being a meaningful top-site mover.

## Key Learning

The ranking needs a historical trend, not two snapshots.

Use weekly or monthly samples, smooth them, and score sustained improvement.

Better concept:

```text
download weekly Tranco snapshots for 6-12 months
calculate each domain's rank over time
smooth ranks with rolling medians
compare recent median rank against older baseline median rank
require repeated presence and consistent improvement
```

## Recommended Cheap Data Stack

### 1. Tranco

Use Tranco as the main free discovery source.

Why:

- Free.
- Has historical daily archives.
- Top-1M CSVs are easy to download.
- Default ranking already combines multiple providers.
- Better than a single raw source for cheap discovery.

Limitations:

- It is rank, not traffic.
- It can still include DNS/infrastructure/noise.
- Rank changes in the long tail are unstable.

### 2. CrUX BigQuery

Use Chrome UX Report as a free validation source for real browser/user popularity.

Why:

- Public historical data.
- Based on real Chrome user experience data.
- Useful to confirm that a domain has real user/browser presence.

Limitations:

- Monthly, not real time.
- Not exact visits.
- Only includes origins that meet popularity and privacy thresholds.

### 3. Cloudflare Radar

Use Radar as a freshness and validation signal.

Why:

- Free API.
- Useful for very recent trending domains.
- Can show `TRENDING_RISE`, `TRENDING_STEADY`, rank, category, and percentage rank change.

Limitations:

- DNS-based, not visit-based.
- Larger ranking datasets are bucketed, not always exactly ordered.
- Tranco already includes Cloudflare Radar as one of its providers, so Radar is partly redundant unless used for freshness or confirmation.

### 4. Paid Traffic Data

Use Similarweb or Semrush only after creating a shortlist.

Why:

- These are closer to actual traffic estimates.
- Useful for validating the final 100-500 domains.
- Can provide visits, users, source mix, geography, device split, and historical traffic.

Limitation:

- Paid and often custom-priced for API access.

## Better Algorithm

Separate two different lists:

- **Sustained growers:** domains with stable, repeated improvement.
- **Breakouts:** domains that were absent or low-ranked, then recently appeared high.

Do not mix these in one ranking. Mixing them caused poor results.

### Sustained Growth Mode

Use weekly Tranco snapshots for 52 weeks.

For each domain:

```text
rank_series = weekly rank, where missing = 1,000,001
log_rank_series = log10(rank_series)
```

Suggested windows:

```text
recent window = last 4 weeks
baseline window = weeks 13-26 before now
trend window = last 12 weeks
```

Metrics:

```text
baseline_rank = median rank in baseline window
recent_rank = median rank in recent window

growth_ratio = baseline_rank / recent_rank
log_growth = log10(baseline_rank) - log10(recent_rank)
```

Quality controls:

```text
presence_rate >= 70%
present in at least 3 of last 4 weeks
recent_rank <= 50,000 or 100,000
improved in at least 60% of week-to-week comparisons
not dominated by one single-week jump
exclude obvious infrastructure/CDN/DNS/adtech/noise
```

Suggested score:

```text
score =
  0.45 * sustained_log_growth
+ 0.25 * twelve_week_trend_slope
+ 0.15 * consistency
+ 0.10 * current_rank_weight
+ 0.05 * cross_source_confirmation
- volatility_penalty
- noise_penalty
```

### Breakout Mode

Use a separate breakout list for newly surging domains.

Suggested criteria:

```text
absent or worse than rank 500,000 for most of history
recent median rank <= 100,000
present in at least 3 of last 4 snapshots
confirmed by Cloudflare Radar, CrUX, or another source
```

Breakouts should be reviewed more carefully because many will be spam, mirrors, campaigns, infrastructure, or measurement artifacts.

## Better Defaults for Current Script

Until the script is upgraded to use many snapshots, use:

```bash
./tranco_growth.py --days-ago 90 --existing-only --exclude-noise --min-gain 1 --max-new-rank 50000 --output tranco-growth-better.csv
```

Why:

- `--min-gain 1` avoids filtering out top-site movements.
- `--max-new-rank 50000` reduces long-tail noise.
- `--existing-only` avoids brand-new top-1M entrants dominating the list.
- `--exclude-noise` removes some obvious infrastructure/adtech/CDN domains.

## Product Direction

The next version should support:

- weekly historical sampling,
- sustained-growth mode,
- breakout mode,
- current top-rank filters,
- supplied domain-list scoring,
- optional Cloudflare Radar validation,
- optional CrUX validation,
- output reason columns explaining why each domain ranked.

Recommended output columns:

```text
domain
score
mode
recent_median_rank
baseline_median_rank
growth_ratio
trend_slope_12w
presence_rate
recent_presence
volatility
current_rank
tranco_confirmed
cloudflare_confirmed
crux_confirmed
noise_flags
```

## Bottom Line

Tranco is good enough for the cheapest first pass, but the algorithm must use a smoothed historical time series. For a credible "fastest-growing websites" list:

1. Use Tranco weekly history for discovery.
2. Separate sustained growers from breakouts.
3. Filter aggressively for rank, presence, consistency, and noise.
4. Validate the shortlist with CrUX and Cloudflare Radar.
5. Use Similarweb or Semrush only when paid traffic validation is worth it.
