---
Task ID: 3
Agent: Main Agent
Task: Integrate Python FastAPI backend with Next.js frontend

Work Log:
- Updated Python backend main.py with 27 OTC trading pairs, expanded MockDataProvider with realistic base prices
- Added convert_signal_for_frontend() function to transform Python engine signals into Next.js-compatible format
- Added dual WebSocket endpoints: /ws (real-time push) and /ws/signals (30s batch push)
- Added background signal generation loop (30s scan cycle) with automatic WebSocket broadcast
- Added REST API endpoints: GET /api/signals/{platform}, POST /api/signals/{id}/close, GET /api/performance
- Created DailyImprover module (backend/app/engine/daily_improver.py) for scheduled weight optimization
- Created requirements.txt with all Python dependencies
- Rewrote use-signal-websocket.ts to use native WebSocket (replaces incompatible socket.io-client)
- Added auto-reconnect with 3-second retry, signal parsing for both new_signal and signals batch events
- Updated page.tsx generateSignals() to try Python backend first, then fallback to internal Next.js generator
- Build verified: `npx next build` compiles successfully
- API verified: Signal generation returns correct martingale data with active WAT times

Stage Summary:
- Python backend outputs signals in Next.js-compatible JSON format
- Frontend connects to Python backend via native WebSocket at ws://localhost:8000/ws
- Dual-source signal generation: Python backend (primary) + Next.js internal (fallback)
- All martingale entry times are correct, active, and displayed in WAT format
- Full integration ready for deployment
