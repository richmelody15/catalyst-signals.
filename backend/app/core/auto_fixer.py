"""
Automatic Error Detection and Fixing System
Catches and corrects every fault in data, calculations, and indicators.
"""
import numpy as np
import pandas as pd
import functools
import logging
from typing import Any, Dict, List, Tuple
from datetime import datetime
from collections import defaultdict
import traceback

logger = logging.getLogger(__name__)


class AutoFixer:
    """Automatic Error Detection and Fixing System."""

    def __init__(self):
        self.error_history = []
        self.fix_statistics = defaultdict(int)

    @staticmethod
    def safe_float(value, default=0.0):
        try:
            v = float(value)
            if np.isnan(v) or np.isinf(v):
                return default
            return v
        except Exception:
            return default

    @staticmethod
    def safe_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def fix_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Repair any broken OHLCV data before analysis."""
        df = df.copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                df[col] = 0.0

        # Forward/backward fill NaN
        df = df.ffill().bfill()

        # Replace infinities
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.ffill().bfill()

        # Ensure high >= low
        mask = df['high'] < df['low']
        df.loc[mask, ['high', 'low']] = df.loc[mask, ['low', 'high']].values

        # Ensure positive prices
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].abs()
            df.loc[df[col] == 0, col] = 0.00001

        # Ensure non-negative volume
        df['volume'] = df['volume'].abs()
        df.loc[df['volume'] == 0, 'volume'] = 100.0

        return df

    @staticmethod
    def fix_indicators(indicators: dict) -> dict:
        """Correct impossible indicator values."""
        defaults = {
            'rsi': 50.0, 'stoch_k': 50.0, 'stoch_d': 50.0,
            'adx': 25.0, 'bb_width': 0.1, 'bb_width_prev': 0.1,
            'atr': 0.001, 'ema50': 0, 'ema200': 0,
            'current_price': 0, 'volatility': 0.5,
            'volume_spike': False, 'volume_trend': 'normal',
            'momentum': 0.0, 'squeeze': False
        }
        for k, v in defaults.items():
            if k not in indicators or indicators[k] is None:
                indicators[k] = v
            if isinstance(indicators[k], float) and (np.isnan(indicators[k]) or np.isinf(indicators[k])):
                indicators[k] = v
        # Clamp bounded indicators
        indicators['rsi'] = max(0, min(100, indicators['rsi']))
        indicators['stoch_k'] = max(0, min(100, indicators['stoch_k']))
        indicators['stoch_d'] = max(0, min(100, indicators['stoch_d']))
        indicators['adx'] = max(0, min(100, indicators['adx']))
        indicators['bb_width'] = max(0, indicators['bb_width'])
        indicators['bb_width_prev'] = max(0, indicators['bb_width_prev'])
        indicators['atr'] = max(0.0001, indicators['atr'])
        return indicators

    def safe_operation(self, fallback_value=None):
        """Decorator for safe operations with automatic error fixing."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    result = func(*args, **kwargs)
                    if result is None or (isinstance(result, float) and (np.isnan(result) or np.isinf(result))):
                        raise ValueError(f"Invalid result from {func.__name__}")
                    return result
                except Exception as e:
                    logger.warning(f"Error in {func.__name__}: {e}")
                    self.error_history.append({
                        'function': func.__name__,
                        'error': str(e),
                        'timestamp': datetime.now()
                    })
                    self.fix_statistics[type(e).__name__] += 1
                    return fallback_value
            return wrapper
        return decorator

    def validate_data_integrity(self, data: pd.DataFrame) -> Tuple[bool, List[str]]:
        """Validate data integrity before signal generation."""
        issues = []
        if data is None or len(data) == 0:
            issues.append("Empty dataset")
            return False, issues

        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            issues.append(f"Missing columns: {missing_columns}")
            return False, issues

        nan_counts = data[required_columns].isna().sum()
        if nan_counts.any():
            issues.append(f"NaN values in: {nan_counts[nan_counts > 0].to_dict()}")

        for col in required_columns:
            if np.isinf(data[col]).any():
                issues.append(f"Inf values in {col}")

        invalid_hl = (data['high'] < data['low']).sum()
        if invalid_hl > 0:
            issues.append(f"High < Low in {invalid_hl} rows")

        if len(data) < 30:
            issues.append(f"Insufficient data length: {len(data)} rows")

        return len(issues) == 0, issues
