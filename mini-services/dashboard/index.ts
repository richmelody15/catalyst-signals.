import { serve } from 'bun';
import { readFileSync } from 'fs';
import { join } from 'path';

const PORT = 8000;
const HTML_PATH = join(import.meta.dir, 'dashboard.html');

let dashboardHTML: string;
try {
  dashboardHTML = readFileSync(HTML_PATH, 'utf-8');
  console.log(`Loaded dashboard HTML: ${dashboardHTML.length} chars`);
} catch (e) {
  console.error('Failed to load dashboard.html:', e);
  dashboardHTML = '<html><body><h1>CATALYST AI Dashboard - Loading Error</h1></body></html>';
}

serve({
  port: PORT,
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    // Main dashboard page
    if (url.pathname === '/' || url.pathname === '') {
      return new Response(dashboardHTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    // API endpoints
    if (url.pathname === '/api/stats') {
      return Response.json({
        total_trades: 0,
        wins: 0,
        losses: 0,
        win_rate: 0,
        ignored: 0,
        pending: 0,
        params: { rsi_buy: 33, rsi_sell: 67, adx_min: 25, vol_mult: 1.5 },
        min_confidence: 80,
      });
    }

    if (url.pathname === '/api/daily-stats') {
      return Response.json({ daily: [] });
    }

    if (url.pathname === '/api/session') {
      return Response.json({
        session: 'Demo',
        active: true,
        time_utc: new Date().toISOString(),
      });
    }

    if (url.pathname === '/api/status') {
      return Response.json({
        status: 'online',
        version: '3.3',
        engine: 'CATALYST FINAL',
        iq_connected: false,
        po_connected: false,
        news_filter: false,
        telegram: false,
        entry_confirm: false,
        scheduler: false,
        connected_clients: 0,
        total_signals_generated: 0,
        params: { rsi_buy: 33, rsi_sell: 67, adx_min: 25, vol_mult: 1.5 },
        min_confidence: 80,
        win_rate: 0,
        total_trades: 0,
        platforms: ['IQ Option', 'Pocket Option'],
        pairs: [
          'EURUSD-OTC', 'GBPJPY-OTC', 'AUDUSD-OTC', 'NZDUSD-OTC',
          'USDCAD-OTC', 'EUR/JPY (OTC)', 'USD/JPY (OTC)', 'EUR/GBP (OTC)',
        ],
        pairs_count: 8,
      });
    }

    if (url.pathname === '/api/signals') {
      return Response.json({ signals: [] });
    }

    // Trade outcome
    if (url.pathname === '/api/trade/outcome' && req.method === 'POST') {
      return Response.json({ status: 'ok' });
    }

    // WebSocket upgrade - return simple response (no WS support in this mini-service)
    if (url.pathname === '/ws') {
      if (req.headers.get('upgrade') === 'websocket') {
        // Return a basic response; the dashboard will handle WS gracefully
        return new Response('WebSocket not available in preview mode', { status: 200 });
      }
      return new Response('OK', { status: 200 });
    }

    return new Response('Not Found', { status: 404 });
  },
});

console.log(`🚀 CATALYST AI Dashboard server running on port ${PORT}`);
