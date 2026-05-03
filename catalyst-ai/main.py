#!/usr/bin/env python3
"""
CATALYST AI - Render Entry Point
uvicorn main:app --host 0.0.0.0 --port 8000

This is the production entry point for Render deployment.
It imports the core engine from catalyst_ai and adds:
  - CORS middleware (frontend on Vercel, backend on Render)
  - Keep-alive self-ping (prevents Render free tier from sleeping)
  - Root health-check endpoint
"""

import asyncio
import os
import logging

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the core engine (all signals, filters, scheduler, etc.)
from catalyst_ai import (
    app as core_app,
    gen,
    latest_signals,
    clients,
    generate_signals,
    Daily95Optimiser,
    logger,
)
from catalyst_ai import AsyncIOScheduler, lifespan as _orig_lifespan

# ── Configuration ────────────────────────────────────────────
RENDER_URL = os.getenv("KEEP_ALIVE_URL", "http://0.0.0.0:8000/")
KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "600"))  # seconds
KEEP_ALIVE_STARTUP_DELAY = 60  # seconds after boot before first ping

# ── New FastAPI app (production wrapper) ─────────────────────
app = FastAPI(
    title="CATALYST AI",
    version="4.1-render",
    lifespan=None,  # we set our own lifespan below
)

# ── CORS: Allow Vercel frontend to call Render backend ───────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://catalyst-ai.vercel.app",
        "https://catalyst-signals.vercel.app",
        "http://localhost:8080",
        "http://localhost:3000",
        "*",  # Allow all during development — tighten in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount all core routes ────────────────────────────────────
# We re-register all the endpoints from catalyst_ai onto this app
# so uvicorn main:app works as the single entry point.

@app.get("/")
async def root():
    """Simple health-check root endpoint (Render wakes up on this)."""
    return {
        "message": "CATALYST AI API is working",
        "status": "online",
        "signals_cached": len(latest_signals),
        "version": "4.1-render",
    }


@app.get("/health")
async def health():
    return {
        "status": "online",
        "signals_cached": len(latest_signals),
        "ws_clients": len(clients),
        "filter_min_overall": gen.filter.min_overall,
        "filter_min_confluences": gen.filter.min_confluences,
        "filter_thresholds": gen.filter.thresholds,
    }


@app.get("/api/signals")
async def api_signals():
    """Return cached signals as JSON."""
    from catalyst_ai import api_signals as _api_signals
    return await _api_signals()


@app.post("/api/generate")
async def api_generate(symbol: str = None, timeframe: str = None):
    from catalyst_ai import api_generate as _api_generate
    return await _api_generate(symbol, timeframe)


@app.post("/api/outcome/{signal_id}")
async def api_outcome(signal_id: str, outcome: str):
    from catalyst_ai import api_outcome as _api_outcome
    return await _api_outcome(signal_id, outcome)


@app.websocket("/ws")
async def ws(websocket):
    from catalyst_ai import ws as _ws
    return await _ws(websocket)


# ── Keep-Alive Self-Ping ────────────────────────────────────
async def keep_alive():
    """
    Periodically ping the server to prevent Render free tier from sleeping.
    Uses httpx AsyncClient for non-blocking HTTP GET.
    """
    await asyncio.sleep(KEEP_ALIVE_STARTUP_DELAY)
    logger.info(f"Keep-alive started: pinging {RENDER_URL} every {KEEP_ALIVE_INTERVAL}s")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(RENDER_URL, timeout=10)
                logger.info(f"Self-ping OK (status={resp.status_code})")
            except Exception as e:
                logger.warning(f"Self-ping failed: {e}")
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)


# ── Lifespan: Scheduler + Keep-Alive ────────────────────────
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup
    scheduler = AsyncIOScheduler()

    # Daily improver at 00:05 WAT
    improver = Daily95Optimiser(gen.filter)
    scheduler.add_job(improver.run, "cron", hour=0, minute=5)

    # Signal generation every 30 seconds
    scheduler.add_job(generate_signals, "interval", seconds=30)

    scheduler.start()

    # Keep-alive task
    keepalive_task = asyncio.create_task(keep_alive())

    logger.info("CATALYST AI started — scheduler + keep-alive active")

    yield

    # Shutdown
    keepalive_task.cancel()
    scheduler.shutdown(wait=False)
    logger.info("CATALYST AI shutting down")


app.router.lifespan_context = lifespan


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
