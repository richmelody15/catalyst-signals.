---
Task ID: 1
Agent: Main Agent
Task: Fix client-side exception in CATALYST AI live preview + integrate risk levels with WAT entry times

Work Log:
- Explored full project structure and identified all client-side exception root causes
- Fixed signal-card.tsx: Added safeToFixed/priceDecimals helpers, null guards for SRLevel.price, glmSmartMoney nested access, riskLevels normalization, WAT timezone formatting using Africa/Lagos
- Fixed signal-store.ts: Added normalizeSignal() function to properly convert API signals (entryTime string→Date, ensure nested objects exist, normalize riskLevels from both number and {multiplier, time} formats)
- Fixed analytics-panel.tsx: Added confAcc safe accessor for confidenceAccuracy with fallback defaults
- Fixed page.tsx: Added null-safe defaults (??) for all performance data fields from API
- Fixed signal-formatter.ts: Added WAT timezone formatting using Africa/Lagos, safeToFixed/priceFmt helpers, null guards on all toFixed() calls, null-safe GLM labels access
- Fixed signal-generator.ts: Updated formatWATTime() to use Africa/Lagos timezone
- Fixed next.config.ts: Added .space-z.site to allowedDevOrigins
- Fixed JSX syntax error in risk levels map (missing closing parenthesis)
- Verified build succeeds with `npx next build`
- Verified API endpoint returns signals with correct risk level format: M1 → 0.7x  Entry Time (22:27 WAT)   ← initial entry

Stage Summary:
- Client-side exception root causes fixed: null property access on SRLevel.price, glmSmartMoney.labels, confidenceAccuracy, riskLevels type mismatches, entryTime string vs Date
- Risk levels now display with WAT entry times in both UI and formatted output
- All timezone formatting uses Africa/Lagos (UTC+1) for WAT compliance
- Build succeeds, standalone server runs and returns HTTP 200
