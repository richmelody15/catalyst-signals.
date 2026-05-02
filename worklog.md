# CATALYST AI - Live Preview Fix Worklog

## Session: 2026-05-02

---
Task ID: 1
Agent: Main Agent
Task: Fix persistent "client-side exception" error in CATALYST AI live preview

Work Log:
- Analyzed all source files in the Next.js project (page.tsx, signal-card.tsx, signal-store.ts, types.ts, layout.tsx, error boundary files, API routes)
- Identified ROOT CAUSE #1: `SafeSignalCard` in page.tsx used try/catch which does NOT catch React render errors — only class-based Error Boundaries with getDerivedStateFromError can catch these errors
- Identified ROOT CAUSE #2: `sonner.tsx` used `useTheme()` from `next-themes` but there was no `ThemeProvider` in the app, which could cause a crash
- Identified ROOT CAUSE #3: Incomplete null guards in signal-card.tsx — deeply nested properties like glmSmartMoney.labels.structure could be undefined
- Identified ROOT CAUSE #4: Signal store normalization could throw on malformed data
- Identified ROOT CAUSE #5: API routes could return NaN/Infinity in numeric fields, which JSON.stringify converts to null but could still cause issues

Fixes Applied:
1. **page.tsx**: Replaced `SafeSignalCard` (try/catch) with `CardErrorBoundary` — a proper React class-based Error Boundary that per-card catches render errors. Also added try/catch around addSignal() calls.
2. **sonner.tsx**: Removed `next-themes` dependency (`useTheme()`) — hardcoded `theme="dark"` since the app uses dark theme by default. This eliminates the ThemeProvider crash.
3. **signal-card.tsx**: Complete rewrite with defensive accessors — every property now goes through `safeStr()`, `safeNum()`, `safeBool()` helper functions. No more direct `.toFixed()`, `.map()`, `.replace()` on potentially null values. Added `isFinite()` checks alongside `typeof` checks.
4. **signal-store.ts**: Made `normalizeSignal()` never-throw with top-level try/catch + fallback. Added `parseEntryTime()`, `normalizeZoneRange()`, `normalizeEngineHealth()` functions. All normalizers now check `isFinite()` for numbers. Strategy array values are filtered with `typeof r === 'string'`.
5. **generate/route.ts**: Added `safeSerializeSignal()` that uses JSON.stringify with a replacer that converts NaN/Infinity to null. Per-pair try/catch so one failure doesn't crash the batch.
6. **live/[platform]/route.ts**: Same safe serialization with NaN/Infinity filtering.

Stage Summary:
- Build: ✅ Successful (no errors)
- SSR: ✅ Renders "Loading CATALYST AI..." state correctly
- Generate API: ✅ Returns complete signal data with M1/M2/M3 risk levels and WAT entry times
- Analytics API: ✅ Returns performance data correctly
- Martingale format: `M1 → 0.7x  Entry Time (06:30 WAT)   ← initial entry`
- The live preview should now work without client-side exceptions
