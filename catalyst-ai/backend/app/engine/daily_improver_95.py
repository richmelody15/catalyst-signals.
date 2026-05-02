import json
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

class Daily95Optimiser:
    def __init__(self, config_path="config/trade_config_95.json", db_path="trading_performance.db"):
        self.config_path = config_path
        self.db_path = db_path
        self.config = self.load_config()

    def load_config(self):
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except:
            return {"min_overall": 92.0, "min_confluences": 8, "thresholds": {"structure":90,"technical":90,"liquidity":90,"zones":85,"volume_momentum":85,"candle_pattern":80}}

    def save_config(self):
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def run(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cutoff = datetime.now() - timedelta(days=7)
        cur.execute("SELECT outcome, feature_scores FROM trades WHERE outcome!='pending' AND entry_time>=?", (cutoff,))
        rows = cur.fetchall()
        conn.close()
        if len(rows) < 20:
            return  # not enough data

        wins = sum(1 for r in rows if r[0]=='win')
        total = len(rows)
        win_rate = wins/total

        # If win rate > 95%, we can slightly relax; if below 95%, tighten
        if win_rate < 0.95:
            self.config['min_overall'] = min(97, self.config['min_overall']+0.5)
            self.config['min_confluences'] = min(10, self.config['min_confluences']+1)
        else:
            # If above 95% for a long time, we can lower a bit to get more signals
            if win_rate > 0.98 and total > 50:
                self.config['min_overall'] = max(90, self.config['min_overall']-0.5)
                self.config['min_confluences'] = max(6, self.config['min_confluences']-1)

        # Adjust per‑feature thresholds based on correlation
        feature_stats = defaultdict(list)
        for r in rows:
            if r[1]:
                scores = json.loads(r[1])
                for k,v in scores.items():
                    feature_stats[k].append((v, 1 if r[0]=='win' else 0))
        for feature, values in feature_stats.items():
            if len(values) < 10: continue
            scores_arr = [v[0] for v in values]
            outcomes = [v[1] for v in values]
            # simple: increase threshold if win rate above it is low
            for th in range(60, 100, 5):
                pass_idx = [i for i,s in enumerate(scores_arr) if s >= th]
                if len(pass_idx) > 5:
                    wr = sum(outcomes[i] for i in pass_idx)/len(pass_idx)
                    if wr >= 0.95:
                        self.config['thresholds'][feature] = th
                        break
        self.save_config()
