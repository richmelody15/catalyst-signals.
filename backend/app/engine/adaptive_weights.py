"""
Adaptive Weight System — Self-Learning Filter Optimization
"""
import sqlite3
import logging
from typing import Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class AdaptiveWeights:
    """
    Self-learning weight optimizer.
    Adjusts indicator weights based on trade outcomes to improve future filtering.
    """

    def __init__(self, db_path="trading_performance.db"):
        self.db_path = db_path
        self.default_weights = {
            'structure': 0.25,
            'technical': 0.20,
            'liquidity': 0.20,
            'zones': 0.15,
            'volume_momentum': 0.20
        }
        self.current_weights = self.default_weights.copy()
        self._load_weights()

    def _load_weights(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS indicator_weights (feature TEXT PRIMARY KEY, weight REAL)")
            cur.execute("SELECT feature, weight FROM indicator_weights")
            for feature, weight in cur.fetchall():
                self.current_weights[feature] = weight
            conn.close()
        except Exception as e:
            logger.warning(f"Could not load weights: {e}")

    def update_from_outcome(self, feature_scores: Dict[str, float], win: bool):
        """Adjust weights slightly after every trade outcome."""
        for feature, score in feature_scores.items():
            if feature not in self.current_weights:
                continue
            adjustment = 0.005 if win else -0.005
            new_w = self.current_weights[feature] + adjustment
            new_w = max(0.05, min(0.40, new_w))
            self.current_weights[feature] = new_w
        self._normalize()
        self._save()

    def _normalize(self):
        total = sum(self.current_weights.values())
        if total > 0:
            for k in self.current_weights:
                self.current_weights[k] /= total

    def _save(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS indicator_weights (feature TEXT PRIMARY KEY, weight REAL)")
            for feature, weight in self.current_weights.items():
                cur.execute("REPLACE INTO indicator_weights VALUES (?, ?)", (feature, weight))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Could not save weights: {e}")
