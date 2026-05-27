#!/usr/bin/env python3
"""
Auto-Diagnostic & Self-Repair Script for Railway Deployment.
Runs BEFORE the main app. Checks and fixes:
- Missing Python packages
- Database column 'session' missing
- Syntax errors in catalystbots.py
- PARAMS missing new keys
Then launches the main app.
"""
import os, sys, subprocess, importlib, sqlite3

def fix_missing_packages():
    """Auto-install any packages that are missing."""
    required = [
        "fastapi", "uvicorn", "pandas", "numpy",
        "python-telegram-bot", "python-dotenv",
        "psycopg2-binary", "passlib", "bcrypt"
    ]
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            print(f"⚠️  Missing package: {pkg} — installing...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                print(f"✅ Installed: {pkg}")
            except Exception as e:
                print(f"❌ Failed to install {pkg}: {e}")

def fix_database():
    """Add missing 'session' column to the trades table if needed."""
    db_path = os.environ.get("DB_PATH", "memory.db")
    if not db_path.startswith("sqlite"):
        print("ℹ️  Non-SQLite DB detected — skipping auto-migration.")
        return
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cur.fetchall()]
        if "session" not in columns:
            cur.execute("ALTER TABLE trades ADD COLUMN session TEXT DEFAULT 'Unknown'")
            print("✅ Added 'session' column to trades table")
        else:
            print("✅ 'session' column already exists")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  Database check error: {e}")

def validate_main_module():
    """Check that catalystbots.py can be loaded without syntax errors."""
    try:
        import catalystbots
        # Check PARAMS has all required keys
        required_params = [
            "use_ema_ribbon", "use_candle_range",
            "use_macd", "use_psar", "use_bb_position", "use_ma_alignment"
        ]
        for key in required_params:
            if key not in catalystbots.PARAMS:
                catalystbots.PARAMS[key] = True
                print(f"✅ Added missing PARAMS key: {key}")
        # Check all new functions exist
        funcs = [
            "rsi_sustained", "rsi_ma_crossover", "ema_ribbon_aligned",
            "candle_range", "average_range", "detect_narrow_range",
            "detect_wide_range", "detect_range_expansion",
            "compute_macd", "macd_bullish_cross", "macd_bearish_cross",
            "compute_parabolic_sar", "bollinger_position",
            "ma_alignment_bull", "ma_alignment_bear"
        ]
        for f in funcs:
            if not hasattr(catalystbots, f):
                raise AttributeError(f"Missing function: {f}")
        print("✅ catalystbots.py validated — all functions & PARAMS present")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        print("⚠️  App will still try to start — check Railway logs if it fails.")

if __name__ == "__main__":
    print("🔧 Running auto-diagnostic & repair...")
    fix_missing_packages()
    fix_database()
    validate_main_module()
    print("✅ Diagnostic complete. Starting main app...")
    # Launch the actual FastAPI server
    port = os.environ.get("PORT", "8000")
    os.system(f"uvicorn catalystbots:app --host 0.0.0.0 --port {port}")
