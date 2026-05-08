---
Task ID: 1
Agent: Main Agent
Task: Build Next.js iframe wrapper for CATALYST AI dashboard + Railway deployment config

Work Log:
- Created SignalDashboard.tsx component with iframe embed, loading states, error handling, and source switching (Railway/Local)
- Updated page.tsx to use SignalDashboard with 'use client' directive for ssr: false compatibility
- Created /dashboard API route that serves the CATALYST dashboard HTML from mini-services/dashboard/dashboard.html
- Extracted DASHBOARD_HTML from catalyst_final.py to mini-services/dashboard/dashboard.html (22,996 chars)
- Created Bun-based mini-service at mini-services/dashboard/ for local Python dashboard serving
- Updated Caddyfile with /py/dashboard proxy route for Python backend
- Created railway.toml and railway.json for Railway deployment configuration
- Created .env.example with all environment variable documentation
- Updated README.md with full Railway deployment instructions, signal format example, and feature documentation
- All files pushed to GitHub (richmelody15/catalyst-signals.)

Stage Summary:
- Next.js app loads at / with iframe embedding CATALYST dashboard
- Dashboard HTML served at /dashboard via Next.js API route (fallback for sandbox)
- Railway deployment ready: Procfile, railway.toml, railway.json, requirements.txt
- All lint checks pass
- v3.3 deployed to GitHub
