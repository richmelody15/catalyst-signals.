---
Task ID: 1
Agent: Main
Task: Set up Render + Vercel deployment stack for CATALYST AI

Work Log:
- Read existing project files (catalyst_ai.py, start.sh, config, daily_improver)
- Created main.py as Render entry point (uvicorn main:app) with keep-alive + CORS middleware
- Created render.yaml with Python 3.11, uvicorn startCommand, KEEP_ALIVE_URL env vars
- Created requirements.txt with fastapi, uvicorn[standard], httpx, pandas, numpy, pytz, apscheduler
- Created frontend/index.html with fetchWithRetry for Render cold start handling
- Created frontend/manifest.json for PWA support
- Created frontend/vercel.json with SPA rewrites
- Created .github/workflows/keep-alive.yml (every 10 min cron)
- Created keep_alive.py standalone pinger script
- Copied frontend to /home/z/my-project/download/catalyst-signals.html

Stage Summary:
- Full deployment stack ready: Render (backend) + Vercel (frontend) + GitHub Actions (keep-alive)
- Frontend fetchWithRetry handles Render cold starts (5 retries, progressive delay 3s→15s)
- Backend has CORS middleware allowing Vercel frontend cross-origin requests
- Backend keep-alive pings every 600s after 60s startup delay
- GitHub Actions pings every 10 min as external wake-up
- Production URL: https://catalyst-backend.onrender.com
