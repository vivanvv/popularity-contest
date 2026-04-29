import unittest

from popularity_contest.scoring import ScoreConfig, breakouts, sustained_growth
from popularity_contest.tranco import Snapshot


def snapshots_for(series_by_domain):
    snapshots = []
    weeks = len(next(iter(series_by_domain.values())))
    for index in range(weeks):
        ranks = {
            domain: series[index]
            for domain, series in series_by_domain.items()
            if series[index] is not None
        }
        snapshots.append(
            Snapshot(
                requested_date=f"202601{index + 1:02d}",
                created_date=f"2026-01-{index + 1:02d}",
                list_id=f"L{index}",
                ranks=ranks,
            )
        )
    return snapshots


class ScoringTests(unittest.TestCase):
    def test_sustained_growth_prefers_repeated_improvement(self):
        snapshots = snapshots_for(
            {
                "steady.example": [
                    90_000,
                    80_000,
                    75_000,
                    70_000,
                    60_000,
                    50_000,
                    40_000,
                    30_000,
                    25_000,
                    20_000,
                    18_000,
                    16_000,
                    15_000,
                ],
                "flat.example": [30_000] * 13,
            }
        )

        rows = sustained_growth(
            snapshots,
            None,
            ScoreConfig(
                baseline_start_weeks_ago=13,
                baseline_end_weeks_ago=5,
                trend_weeks=8,
                min_presence_rate=1.0,
                max_recent_rank=100_000,
            ),
        )

        self.assertEqual(rows[0]["domain"], "steady.example")
        self.assertGreater(rows[0]["growth_ratio"], 1)

    def test_breakout_detects_recent_presence_after_absence(self):
        snapshots = snapshots_for(
            {
                "new.example": [None, None, None, None, None, None, 40_000, 30_000, 20_000, 18_000],
                "old.example": [40_000] * 10,
            }
        )

        rows = breakouts(snapshots, None, ScoreConfig(max_recent_rank=100_000))

        self.assertEqual(rows[0]["domain"], "new.example")


if __name__ == "__main__":
    unittest.main()
