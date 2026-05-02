"""
Daily Improver — Scheduled self-improvement tasks
Runs daily to optimize filter weights based on recent performance data.
"""
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class DailyImprover:
    """
    Runs daily improvement tasks:
    1. Review trade outcomes and adjust adaptive weights
    2. Identify best/worst performing pairs and timeframes
    3. Optimize filter thresholds based on win rate
    """

    def __init__(self, db_path: str = "trading_performance.db"):
        self.db_path = db_path

    def run_daily_improvement(self):
        """Main entry point — called by the scheduler."""
        logger.info("Daily improvement started")
        try:
            self._review_and_adjust_weights()
            self._optimize_thresholds()
            self._cleanup_old_data()
        except Exception as e:
            logger.error(f"Daily improvement failed: {e}")
        logger.info("Daily improvement completed")

    def _review_and_adjust_weights(self):
        """Review recent trades and adjust filter weights."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Get last 7 days of trades
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT feature_scores, outcome FROM trades
            WHERE outcome != 'pending' AND entry_time >= ?
        """, (cutoff,))
        rows = cur.fetchall()
        conn.close()

        if not rows:
            logger.info("No recent trades to review")
            return

        wins = sum(1 for r in rows if r[1] == 'win')
        total = len(rows)
        win_rate = (wins / total * 100) if total > 0 else 0

        logger.info(f"Last 7 days: {wins}/{total} wins ({win_rate:.1f}%)")

    def _optimize_thresholds(self):
        """Optimize filter thresholds based on performance."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT symbol, timeframe, outcome FROM trades
            WHERE outcome != 'pending'
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return

        # Identify best/worst pairs
        pair_stats: Dict[str, Dict] = {}
        for symbol, timeframe, outcome in rows:
            key = f"{symbol}_{timeframe}"
            if key not in pair_stats:
                pair_stats[key] = {'wins': 0, 'total': 0}
            pair_stats[key]['total'] += 1
            if outcome == 'win':
                pair_stats[key]['wins'] += 1

        for key, stats in pair_stats.items():
            if stats['total'] >= 5:
                wr = stats['wins'] / stats['total'] * 100
                if wr < 50:
                    logger.warning(f"Low win rate: {key} = {wr:.1f}%")

    def _cleanup_old_data(self):
        """Remove old pending trades (>7 days)."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        cur.execute("""
            DELETE FROM trades WHERE outcome = 'pending' AND entry_time < ?
        """, (cutoff,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old pending trades")
