# Popularity Contest

Popularity Contest ranks websites whose public popularity signals are improving.

The project uses Tranco as the first data source. That means the output is a popularity ranking, not an estimate of exact visits, users, or revenue.

## Install

```bash
python3 -m pip install -e .
```

## Run

Best default:

```bash
popularity-contest sustained --weeks 26 --top 100 --output data/outputs/sustained.csv
```

Other useful runs:

```bash
# Newly emerging domains. Review these more aggressively.
popularity-contest breakout --weeks 26 --top 100 --output data/outputs/breakouts.csv

# Score only a supplied watchlist.
popularity-contest sustained --domains domains.txt --weeks 26

# Generate both ranked lists.
popularity-contest all --weeks 26 --output-dir data/outputs
```

## Repository Layout

```text
src/popularity_contest/
  cli.py        CLI orchestration.
  domains.py    Domain normalization and noise flags.
  export.py     CSV output.
  scoring.py    Sustained-growth and breakout scoring.
  tranco.py     Tranco API access and cache.

docs/
  methodology.md
  fastest-growing-websites-learnings.md

data/
  cache/        Downloaded source snapshots.
  outputs/      Generated ranked CSVs.

tests/
  Unit tests for scoring and domain handling.
```

## Methodology

See [docs/methodology.md](docs/methodology.md).

