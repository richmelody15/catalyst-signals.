---
Task ID: 1
Agent: Main Agent
Task: Fix client-side exception error in CATALYST AI preview deployment

Work Log:
- Analyzed the full project structure (Next.js 16 trading dashboard with Zustand, Socket.io, Prisma)
- Identified root causes of the "Application error: a client-side exception has occurred":
  1. Cross-origin request blocking: next.config.ts missing allowedDevOrigins for preview domains
  2. Unsafe null/undefined property access in signal-card.tsx (glmSmartMoney.labels, nearestSupport.price.toFixed, mtfConfluence.timeframeResults, etc.)
  3. Unsafe array method calls on potentially null arrays (strategy.entryRules.map, strategy.exitRules.map)
  4. Missing null guards in signal-history.tsx for nearestSupport/nearestResistance price formatting
  5. Date formatting functions that could throw on invalid dates

- Applied fixes:
  1. Added `allowedDevOrigins: [".space-z.ai", ".space.chatglm.site"]` to next.config.ts
  2. Added safe accessor variables in signal-card.tsx (strategy, glmSmartMoney, mtfConfluence, nearestSDZone, zoneInteraction, engineHealth, nearestSupport, nearestResistance, supportZone, resistanceZone)
  3. Added null-safe optional chaining for glmSmartMoney.labels (?.structure, ?.liquidity, etc.)
  4. Added fallback empty arrays for strategy rules (strategy.entryRules || [])
  5. Added null guards for zone price formatting (supportZone.start != null checks, ?.toFixed())
  6. Added null checks for zoneInteraction properties (stopLoss?.toFixed, entryPrice?.toFixed, etc.)
  7. Added try/catch in formatEntryTime() with fallback "--:-- WAT"
  8. Added try/catch in SignalHistory formatTime() with fallback "--:-- WAT"
  9. Added null check for signal.nearestSupport.price in signal-history.tsx

Stage Summary:
- All client-side null reference errors should now be caught
- Cross-origin resource loading is now allowed for the preview domain
- The page compiles and renders successfully (HTTP 200)
- Dev server needs restart for next.config.ts changes to take effect
