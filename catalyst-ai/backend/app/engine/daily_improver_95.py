"""
Daily95Optimiser — Self-improving filter threshold optimizer
Adjusts UltraFilter thresholds based on recent win rate and per-feature performance.
Persists config to JSON so changes survive restarts.

This module is imported and used by catalyst_ai.py via the integrated
Daily95Optimiser class. This file can also be run standalone for testing.
"""
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

DB_PATH = "trading_performance.db"
CONFIG_PATH = "config/trade_config_95.json"


class Daily95Optimiser:
    """
    Daily self-improvement engine that adjusts the UltraFilter's
    min_overall, min_confluences, and per-feature thresholds
    based on the last 7 days of trade performance.

    Logic:
      - If recent win rate < 95%: tighten (raise min_overall +0.5, confluences +1)
      - If recent win rate > 98% with 50+ trades: relax (lower min_overall -0.5, confluences -1)
      - Per-feature: find the lowest threshold where win rate >= 95% for that feature
    """

    def __init__(self, filter_obj=None, config_path=CONFIG_PATH, db_path=DB_PATH):
        self.filter = filter_obj
        self.config_path = config_path
        self.db_path = db_path
        self.config = self._load_config()

    def _load_config(self):
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except Exception:
            return {
                "min_overall": 92.0,
                "min_confluences": 8,
                "thresholds": {
                    "structure": 90, "technical": 90, "liquidity": 90,
                    "zones": 85, "volume_momentum": 85, "candle_pattern": 80,
                },
            }

    def _save_config(self):
        if self.filter:
            self.config["min_overall"] = self.filter.min_overall
            self.config["min_confluences"] = self.filter.min_confluences
            self.config["thresholds"] = dict(self.filter.thresholds)
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def run(self):
        """Main improvement run - called by scheduler."""
        logger.info("Daily95Optimiser: starting improvement cycle")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cutoff = datetime.now() - timedelta(days=7)
        cur.execute(
            "SELECT outcome, feature_scores FROM trades WHERE outcome!='pending' AND entry_time>=?",
            (cutoff.isoformat(),),
        )
        rows = cur.fetchall()
        conn.close()

        if len(rows) < 20:
            logger.info("Daily95Optimiser: not enough data (<20 trades), skipping")
            self._save_config()
            return

        # Win rate based adjustment
        wins = sum(1 for r in rows if r[0] == "win")
        total = len(rows)
        win_rate = wins / total

        if self.filter:
            if win_rate < 0.95:
                self.filter.min_overall = min(97, self.filter.min_overall + 0.5)
                self.filter.min_confluences = min(10, self.filter.min_confluences + 1)
            elif win_rate > 0.98 and total > 50:
                self.filter.min_overall = max(90, self.filter.min_overall - 0.5)
                self.filter.min_confluences = max(6, self.filter.min_confluences - 1)

            # Per-feature threshold optimisation
            feature_stats = defaultdict(list)
            for r in rows:
                if r[1]:
                    try:
                        scores = json.loads(r[1])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    for k, v in scores.items():
                        feature_stats[k].append((v, 1 if r[0] == "win" else 0))

            for feature, values in feature_stats.items():
                if len(values) < 10:
                    continue
                scores_arr = [v[0] for v in values]
                outcomes = [v[1] for v in values]
                for th in range(60, 100, 5):
                    pass_idx = [i for i, s in enumerate(scores_arr) if s >= th]
                    if len(pass_idx) > 5:
                        wr = sum(outcomes[i] for i in pass_idx) / len(pass_idx)
                        if wr >= 0.95:
                            if feature in self.filter.thresholds:
                                self.filter.thresholds[feature] = th
                            break

        logger.info(
            f"Daily95Optimiser: wr={win_rate:.2%}, "
            f"min_overall={self.filter.min_overall if self.filter else 'N/A'}, "
            f"min_confluences={self.filter.min_confluences if self.filter else 'N/A'}"
        )
        self._save_config()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    optimiser = Daily95Optimiser()
    optimiser.run()
