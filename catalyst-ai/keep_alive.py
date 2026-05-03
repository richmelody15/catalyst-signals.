#!/usr/bin/env python3
"""
CATALYST AI — Standalone Keep-Alive Script
Run this on any machine to periodically ping your Render backend
and prevent it from sleeping on the free tier.

Usage:
  python keep_alive.py --url https://catalyst-backend.onrender.com --interval 420
"""

import argparse
import time
import logging

try:
    import httpx
except ImportError:
    import urllib.request
    httpx = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] keep-alive: %(message)s",
)
logger = logging.getLogger("keep-alive")


def ping_urllib(url: str) -> int:
    """Fallback pinger using urllib (no httpx needed)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception as e:
        logger.error(f"Ping failed (urllib): {e}")
        return 0


def ping_httpx(url: str) -> int:
    """Preferred pinger using httpx."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url)
            return resp.status_code
    except Exception as e:
        logger.error(f"Ping failed (httpx): {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="CATALYST AI Keep-Alive Pinger")
    parser.add_argument("--url", default="https://catalyst-backend.onrender.com/health",
                        help="Backend URL to ping")
    parser.add_argument("--interval", type=int, default=420,
                        help="Seconds between pings (default: 420 = 7 min)")
    args = parser.parse_args()

    ping_fn = ping_httpx if httpx else ping_urllib
    logger.info(f"Keep-alive started: pinging {args.url} every {args.interval}s")
    logger.info(f"Using {'httpx' if httpx else 'urllib'} for HTTP requests")

    while True:
        status = ping_fn(args.url)
        if 200 <= status < 300:
            logger.info(f"Self-ping OK (status={status})")
        elif status == 0:
            logger.warning("Self-ping failed (connection error)")
        else:
            logger.warning(f"Self-ping returned status={status} (backend may be waking up)")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
