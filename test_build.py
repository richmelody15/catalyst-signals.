#!/usr/bin/env python3
"""Quick validation of the v5.5 engine before pushing to Railway."""
import sys
import importlib.util

# Load the main module
spec = importlib.util.spec_from_file_location("catalystbots", "catalystbots.py")
try:
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("✅ Module loaded successfully.")
except Exception as e:
    print(f"❌ Module failed to load: {e}")
    sys.exit(1)

# Check that the new functions exist
required_functions = [
    "rsi_sustained", "rsi_ma_crossover", "ema_ribbon_aligned",
    "candle_range", "average_range", "detect_narrow_range",
    "detect_wide_range", "detect_range_expansion",
    "compute_macd", "macd_bullish_cross", "macd_bearish_cross",
    "compute_parabolic_sar", "bollinger_position",
    "ma_alignment_bull", "ma_alignment_bear"
]
all_ok = True
for func_name in required_functions:
    if not hasattr(mod, func_name):
        print(f"❌ Missing function: {func_name}")
        all_ok = False
    else:
        print(f"✅ Function found: {func_name}")

# Check that PARAMS contains new keys
params = getattr(mod, "PARAMS", {})
new_keys = [
    "use_ema_ribbon", "use_candle_range",
    "use_macd", "use_psar", "use_bb_position", "use_ma_alignment"
]
for key in new_keys:
    if key in params:
        print(f"✅ PARAMS key found: {key} = {params[key]}")
    else:
        print(f"❌ Missing PARAMS key: {key}")
        all_ok = False

# Quick functional test with dummy data
try:
    import pandas as pd
    import numpy as np
    n = 100
    np.random.seed(42)
    closes = 1.0 + np.cumsum(np.random.randn(n) * 0.001)
    highs = closes + np.abs(np.random.randn(n) * 0.0005)
    lows = closes - np.abs(np.random.randn(n) * 0.0005)
    volumes = np.random.randint(100, 1000, n).astype(float)
    df = pd.DataFrame({
        'open': closes - np.random.randn(n) * 0.0002,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })

    # Test each function with the dummy data
    tests = {
        "rsi_sustained": lambda: mod.rsi_sustained(df, 'BUY'),
        "rsi_ma_crossover": lambda: mod.rsi_ma_crossover(df, 'BUY'),
        "ema_ribbon_aligned": lambda: mod.ema_ribbon_aligned(df, 'BUY'),
        "detect_narrow_range": lambda: mod.detect_narrow_range(df),
        "detect_wide_range": lambda: mod.detect_wide_range(df),
        "detect_range_expansion": lambda: mod.detect_range_expansion(df),
        "macd_bullish_cross": lambda: mod.macd_bullish_cross(df),
        "macd_bearish_cross": lambda: mod.macd_bearish_cross(df),
        "compute_parabolic_sar": lambda: mod.compute_parabolic_sar(df),
        "bollinger_position": lambda: mod.bollinger_position(df),
        "ma_alignment_bull": lambda: mod.ma_alignment_bull(df),
        "ma_alignment_bear": lambda: mod.ma_alignment_bear(df),
    }
    for name, fn in tests.items():
        try:
            result = fn()
            print(f"✅ {name}() returned: {result}")
        except Exception as e:
            print(f"❌ {name}() raised: {e}")
            all_ok = False

except Exception as e:
    print(f"❌ Functional tests failed: {e}")
    all_ok = False

if all_ok:
    print("\n🎉 All checks passed! Safe to push to GitHub/Railway.")
else:
    print("\n⚠️  Some checks failed. Fix before deploying.")
    sys.exit(1)
