import { NextResponse } from 'next/server';
import { readFileSync } from 'fs';
import { join } from 'path';

let dashboardHTML: string | null = null;

function getDashboardHTML(): string {
  if (dashboardHTML) return dashboardHTML;

  try {
    const htmlPath = join(process.cwd(), 'mini-services/dashboard/dashboard.html');
    dashboardHTML = readFileSync(htmlPath, 'utf-8');
    return dashboardHTML;
  } catch {
    return `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>CATALYST AI</title></head>
<body style="background:#050510;color:#e0e0e0;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif">
<div style="text-align:center">
<h2>CATALYST AI Dashboard</h2>
<p style="color:#888">Deploy to Railway for live signals</p>
<p style="color:#666;font-size:12px">Railway URL: https://catalyst-signals.up.railway.app</p>
</div>
</body>
</html>`;
  }
}

export async function GET() {
  const html = getDashboardHTML();
  return new NextResponse(html, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-cache',
    },
  });
}
