---
Task ID: 1
Agent: Main Agent
Task: Fix client-side exception and enhance risk level display

Work Log:
- Analyzed entire codebase (30+ files) to identify crash sources
- Identified multiple potential crash points: NaN values in Progress component, unsafe .startsWith() in signal-formatter, missing null guards in signal-history
- Added NaN guards for signal.confidence, signal.rsiValue, signal.riskReward, signal.checklistScore in signal-card.tsx
- Added safeConfidence variable to prevent NaN in Progress component
- Fixed signal-formatter.ts: Changed `glm.breakout.startsWith('CONFIRMED')` to `(glm.breakout ?? '').startsWith('CONFIRMED')` to prevent TypeError
- Added comprehensive null/type checks in signal-history.tsx for price.toFixed() calls
- Created SafeSignalCard wrapper in page.tsx with try/catch to prevent individual signal cards from crashing the entire page
- Enhanced ErrorBoundary component to show actual error message and component stack trace
- Enhanced error.tsx to display error digest for debugging
- Updated risk level display to match Python format: "Martingale Recovery (Risk Level)" with "← initial entry" only on M1
- Added "Trade 1% - 3% of your capability and capital" note to risk levels
- Updated signal-formatter.ts risk level output in all 3 formats (plain, emoji, detailed) to match Python format
- Updated copy signal text to include "Note: Trade 1% - 3%..." and "SIGNAL STATUS" lines
- Verified build succeeds with no errors
- Tested page rendering with agent-browser - no client-side exceptions

Stage Summary:
- Client-side exception is fixed - page renders correctly with no errors
- Risk levels now display with proper entry times in WAT format matching Python output
- Added per-card error boundary to prevent cascade failures
- All NaN/null guards in place for numeric display values
