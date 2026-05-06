---
Task ID: 1
Agent: main
Task: Consolidate all CATALYST signal system versions into one definitive file with bug fixes

Work Log:
- Analyzed ~15 different code iterations provided by user (CATALYST FINAL through CATALYST PRO MAX)
- Identified critical bugs: close[:-1] pandas Series slicing, bb_width with wrong indexing, missing endpoints
- Consolidated best features from all versions into single catalyst_final.py
- Fixed all pandas Series slicing bugs (close[:-1] -> close.iloc[:-1])
- Fixed bb_width(close[:-1], 20) -> bb_width(close.iloc[:-1], 20)
- Fixed market_structure duplicate condition logic
- Added proper index alignment for ADX plus_dm/minus_dm Series
- Made order_block and FVG soft confirmations (won't block signal if absent)
- Relaxed parameters for 5-10 signals/session (rsi_buy:33, rsi_sell:67, adx_min:25, vol_mult:1.5)
- Added /api/status endpoint, /api/signals endpoint
- Added params display in stats bar
- Removed ML/SGDClassifier dependency (no real training data; memory system is sufficient)
- Updated requirements.txt to only need fastapi, uvicorn, pandas, numpy
- Tested server: all endpoints working, dashboard renders correctly

Stage Summary:
- Produced: /home/z/my-project/download/catalyst_final.py (consolidated, bug-fixed version)
- Produced: /home/z/my-project/download/requirements.txt
- Key improvements: Fixed 3 critical pandas bugs, made OB/FVG soft filters, relaxed params for more signals
- Server tested and confirmed working on port 8765
