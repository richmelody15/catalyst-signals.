// CATALYST AI - Signal Formatter
// Emoji-rich signal output formatting for multiple display contexts
// Converts Signal objects into formatted text for copy/share/telegram

import type { Signal, FormattedSignal, MTFConfluence, SupplyDemandZone, ZoneInteraction, GLMSmartMoneyResult } from './types';

/**
 * Format a signal in multiple output styles.
 */
export class SignalFormatter {

  /**
   * Format a signal in all available styles.
   */
  format(signal: Signal): FormattedSignal {
    return {
      plain: this.formatPlain(signal),
      emoji: this.formatEmoji(signal),
      compact: this.formatCompact(signal),
      detailed: this.formatDetailed(signal),
    };
  }

  /**
   * Plain text format — no emojis, clean layout.
   */
  formatPlain(signal: Signal): string {
    const lines: string[] = [
      `CATALYST AI SIGNAL`,
      ``,
      `Trade: ${signal.tradePair}`,
      `Timer: ${signal.timer}`,
      `Entry: ${this.formatTime(signal.entryTime)}`,
      `Direction: ${signal.direction}`,
      `GLM Probability: ${signal.glmProbability}% WIN RATE`,
      `Confidence: ${signal.confidence}%`,
      `Market: ${signal.marketCondition}`,
      ``,
      `Trend: ${signal.trend}`,
      `BOS: ${signal.bosConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `CHoCH: ${signal.chochConfirmed ? 'Confirmed' : 'Not Confirmed'}`,
      `FVG: ${signal.fvgActive ? 'Active' : 'Not Active'}`,
      `Liquidity: ${signal.liquiditySweep ? 'Sweep Detected' : 'None'}`,
      `Volume: ${signal.volumeHigh ? 'High' : 'Normal'}`,
      `Zone: ${signal.zoneType}`,
      `RSI: ${signal.rsiValue}`,
      `Stochastic: ${signal.stochasticBull ? 'Bullish Crossover' : 'Neutral'}`,
      `BB Width: ${signal.bbExpanding ? 'Expanding' : 'Contracting'}`,
      `R:R: 1:${signal.riskReward}`,
      ``,
      `Regime: ${signal.regimeLabel}`,
      `Checklist Score: ${signal.checklistScore}%`,
    ];

    // MTF Confluence
    if (signal.mtfConfluence) {
      lines.push('', 'MTF CONFLUENCE:');
      lines.push(...this.formatMTFPlain(signal.mtfConfluence));
    }

    // S/D Zone
    if (signal.nearestSDZone) {
      lines.push('', 'SUPPLY/DEMAND ZONE:');
      lines.push(...this.formatZonePlain(signal.nearestSDZone));
    }

    // Zone Interaction
    if (signal.zoneInteraction) {
      lines.push('', 'ZONE INTERACTION:');
      lines.push(...this.formatInteractionPlain(signal.zoneInteraction));
    }

    // GLM Smart Money Engine
    if (signal.glmSmartMoney) {
      lines.push('', 'GLM SMART MONEY:');
      lines.push(...this.formatGLMSmartMoneyPlain(signal.glmSmartMoney));
    }

    // Risk Levels
    lines.push('', 'RISK LEVELS:');
    const riskEntriesPlain = Object.entries(signal.riskLevels);
    for (let i = 0; i < riskEntriesPlain.length; i++) {
      const [key, level] = riskEntriesPlain[i];
      const mult = typeof level === 'object' && level !== null && 'multiplier' in level ? level.multiplier : level;
      const time = typeof level === 'object' && level !== null && 'time' in level ? level.time : '';
      lines.push(`  ${key} -> ${mult}x  Entry Time (${time})   ← initial entry`);
    }

    // Engine Health
    if (signal.engineHealth) {
      lines.push('', 'ENGINE HEALTH:');
      lines.push(`  Errors Recovered: ${signal.engineHealth.errorsRecovered}`);
      lines.push(`  Recovery Rate: ${signal.engineHealth.recoveryRate}%`);
    }

    return lines.join('\n');
  }

  /**
   * Emoji-rich format — full visual presentation with emoji indicators.
   */
  formatEmoji(signal: Signal): string {
    const isBuy = signal.direction === 'BUY';
    const dirEmoji = isBuy ? '🟢' : '🔴';
    const arrow = isBuy ? '📈' : '📉';

    const lines: string[] = [
      `🔔 CATALYST AI SIGNAL!`,
      ``,
      `${dirEmoji} Trade: ${signal.tradePair}`,
      `⏳ Timer: ${signal.timer}`,
      `➡️ Entry: ${this.formatTime(signal.entryTime)}`,
      `${arrow} Direction: ${signal.direction}`,
      `🎯 GLM Probability: ${signal.glmProbability}% WIN RATE`,
      `📊 Market: ${signal.marketCondition}`,
      ``,
      `🔮 Market Regime: ${signal.regimeLabel}`,
      `   ${signal.regimeDescription}`,
      ``,
      `🧠 Trend: ${signal.trend}`,
      `📉 BOS: ${signal.bosConfirmed ? '✅ Confirmed' : '❌ Not Confirmed'}`,
      `🔄 CHoCH: ${signal.chochConfirmed ? '✅ Confirmed' : '❌ Not Confirmed'}`,
      `📦 FVG: ${signal.fvgActive ? '✅ Active' : '❌ Not Active'}`,
      `💧 Liquidity: ${signal.liquiditySweep ? '✅ Sweep Detected' : '❌ None'}`,
      `📦 Volume: ${signal.volumeHigh ? '🔥 High' : '📊 Normal'}`,
      `🏗️ Zone: ${signal.zoneType}`,
      `📉 RSI: ${signal.rsiValue}`,
      `📊 Stochastic: ${signal.stochasticBull ? '🐂 Bullish Crossover' : '😐 Neutral'}`,
      `📊 BB Width: ${signal.bbExpanding ? '📐 Expanding' : '📏 Contracting'}`,
      `⚖️ RR: 1:${signal.riskReward}`,
    ];

    // MTF Confluence
    if (signal.mtfConfluence) {
      lines.push('', '🕐 MULTI-TIMEFRAME ANALYSIS:');
      lines.push(...this.formatMTFEmoji(signal.mtfConfluence));
    }

    // S/D Zone
    if (signal.nearestSDZone) {
      lines.push('', '🏷️ SUPPLY/DEMAND ZONE:');
      lines.push(...this.formatZoneEmoji(signal.nearestSDZone));
    }

    // Zone Interaction
    if (signal.zoneInteraction) {
      lines.push('', '⚡ ZONE INTERACTION:');
      lines.push(...this.formatInteractionEmoji(signal.zoneInteraction));
    }

    // GLM Smart Money Engine
    if (signal.glmSmartMoney) {
      lines.push('', '🧪 GLM SMART MONEY:');
      lines.push(...this.formatGLMSmartMoneyEmoji(signal.glmSmartMoney));
    }

    // Risk Levels
    lines.push('', '↪️ Risk Levels:');
    const riskEntries = Object.entries(signal.riskLevels);
    for (let i = 0; i < riskEntries.length; i++) {
      const [key, level] = riskEntries[i];
      const mult = typeof level === 'object' && level !== null && 'multiplier' in level ? level.multiplier : level;
      const time = typeof level === 'object' && level !== null && 'time' in level ? level.time : '';
      lines.push(`  ${key} → ${mult}x  Entry Time (${time})   ← initial entry`);
    }

    // Strategy Guide (compact)
    if (signal.strategy) {
      lines.push('', '📋 STRATEGY GUIDE:');
      for (const rule of signal.strategy.entryRules) {
        lines.push(`  ✅ ${rule}`);
      }
      for (const rule of signal.strategy.exitRules) {
        lines.push(`  🚪 ${rule}`);
      }
      for (const rule of signal.strategy.riskManagement) {
        lines.push(`  🛡️ ${rule}`);
      }
    }

    // Engine Health
    if (signal.engineHealth && signal.engineHealth.errorsRecovered > 0) {
      lines.push('', `🔧 Engine: ${signal.engineHealth.errorsRecovered} errors auto-recovered (${signal.engineHealth.recoveryRate}% rate)`);
    }

    lines.push('', `🎯 GLM PROBABILITY: ${signal.glmProbability}% WIN RATE`);
    lines.push(`   ${signal.signalQuality}`);

    return lines.join('\n');
  }

  /**
   * Compact format — single-line summary for quick scanning.
   */
  formatCompact(signal: Signal): string {
    const isBuy = signal.direction === 'BUY';
    const dir = isBuy ? '🟢 BUY' : '🔴 SELL';
    const mtfAligned = signal.mtfConfluence?.aligned ? ' MTF✅' : '';
    const zoneStr = signal.nearestSDZone
      ? ` Zone:${signal.nearestSDZone.type}(${signal.nearestSDZone.strength})`
      : '';

    return `${dir} ${signal.tradePair} ${signal.timer} | Conf:${signal.confidence}% GLM:${signal.glmProbability}% | ${signal.regimeLabel}${mtfAligned}${zoneStr} | Checklist:${signal.checklistScore}%`;
  }

  /**
   * Detailed format — full breakdown with all analysis data.
   */
  formatDetailed(signal: Signal): string {
    const isBuy = signal.direction === 'BUY';
    const lines: string[] = [
      `═══════════════════════════════════════`,
      `  CATALYST AI — DETAILED SIGNAL REPORT`,
      `═══════════════════════════════════════`,
      ``,
      `TRADE INFORMATION`,
      `─────────────────`,
      `  Pair: ${signal.tradePair}`,
      `  Timer: ${signal.timer}`,
      `  Entry Time: ${this.formatTime(signal.entryTime)}`,
      `  Direction: ${signal.direction}`,
      `  Confidence: ${signal.confidence}%`,
      `  GLM Probability: ${signal.glmProbability}%`,
      `  Signal Quality: ${signal.signalQuality}`,
      `  Checklist Score: ${signal.checklistScore}%`,
      ``,
      `MARKET ANALYSIS`,
      `─────────────────`,
      `  Condition: ${signal.marketCondition}`,
      `  Trend: ${signal.trend}`,
      `  Market Regime: ${signal.regimeLabel}`,
      `  Regime Description: ${signal.regimeDescription}`,
      ``,
      `TECHNICAL INDICATORS`,
      `─────────────────`,
      `  RSI: ${signal.rsiValue}`,
      `  Stochastic: ${signal.stochasticBull ? 'Bullish Crossover' : 'Neutral'}`,
      `  BB Width: ${signal.bbExpanding ? 'Expanding' : 'Contracting'}`,
      `  Zone Type: ${signal.zoneType}`,
      `  ADR Status: ${signal.adrStatus}`,
      `  Risk:Reward: 1:${signal.riskReward}`,
    ];

    // Smart Money Concepts
    lines.push('', 'SMART MONEY CONCEPTS', '─────────────────');
    lines.push(`  BOS: ${signal.bosConfirmed ? '✅' : '❌'}`);
    lines.push(`  CHoCH: ${signal.chochConfirmed ? '✅' : '❌'}`);
    lines.push(`  FVG: ${signal.fvgActive ? '✅' : '❌'}`);
    lines.push(`  Liquidity Sweep: ${signal.liquiditySweep ? '✅' : '❌'}`);
    lines.push(`  Volume Spike: ${signal.volumeHigh ? '✅' : '❌'}`);

    // S/R Zones
    if (signal.nearestSupport || signal.nearestResistance) {
      lines.push('', 'SUPPORT/RESISTANCE', '─────────────────');
      if (signal.nearestSupport) {
        const s = signal.nearestSupport;
        lines.push(`  Support: ${s.price.toFixed(s.price < 100 ? 4 : 2)} (Strength: ${s.strength}${s.isMajor ? ', Major' : ''})`);
      }
      if (signal.nearestResistance) {
        const r = signal.nearestResistance;
        lines.push(`  Resistance: ${r.price.toFixed(r.price < 100 ? 4 : 2)} (Strength: ${r.strength}${r.isMajor ? ', Major' : ''})`);
      }
    }

    // MTF Analysis
    if (signal.mtfConfluence) {
      lines.push('', 'MULTI-TIMEFRAME ANALYSIS', '─────────────────');
      lines.push(`  Aligned: ${signal.mtfConfluence.aligned ? '✅ YES' : '❌ NO'}`);
      lines.push(`  Alignment Score: ${signal.mtfConfluence.alignmentScore}%`);
      lines.push(`  Dominant Trend: ${signal.mtfConfluence.dominantTrend}`);
      lines.push(`  Bullish TFs: ${signal.mtfConfluence.bullishCount} | Bearish: ${signal.mtfConfluence.bearishCount} | Neutral: ${signal.mtfConfluence.neutralCount}`);

      // Checklist
      lines.push('', '  8-POINT MTF CHECKLIST:');
      const mtfCheck = signal.mtfConfluence.checklist;
      lines.push(`    Higher TF Alignment: ${mtfCheck.higher_tf_trend_alignment ? '✅' : '❌'}`);
      lines.push(`    Structure Break: ${mtfCheck.structure_break_confirmed ? '✅' : '❌'}`);
      lines.push(`    Momentum Convergence: ${mtfCheck.momentum_convergence ? '✅' : '❌'}`);
      lines.push(`    Volume Confirm: ${mtfCheck.volume_confirmation ? '✅' : '❌'}`);
      lines.push(`    RSI Divergence OK: ${mtfCheck.rsi_divergence_check ? '✅' : '❌'}`);
      lines.push(`    EMA Stack: ${mtfCheck.ema_stack_alignment ? '✅' : '❌'}`);
      lines.push(`    Volatility Filter: ${mtfCheck.volatility_filter ? '✅' : '❌'}`);
      lines.push(`    Liquidity Proximity: ${mtfCheck.liquidity_pool_proximity ? '✅' : '❌'}`);
      lines.push(`    Score: ${signal.mtfConfluence.checklistScore}%`);
    }

    // S/D Zone
    if (signal.nearestSDZone) {
      lines.push('', 'SUPPLY/DEMAND ZONE', '─────────────────');
      const z = signal.nearestSDZone;
      lines.push(`  Type: ${z.type} (${z.direction})`);
      lines.push(`  Range: ${z.low.toFixed(5)} - ${z.high.toFixed(5)}`);
      lines.push(`  Strength: ${z.strength} | Belief: ${z.beliefScore}%`);
      lines.push(`  Touches: ${z.touches} | Hold Rate: ${z.performance.holdRate}%`);
    }

    // Zone Interaction
    if (signal.zoneInteraction) {
      lines.push('', 'ZONE INTERACTION SIGNAL', '─────────────────');
      const zi = signal.zoneInteraction;
      lines.push(`  Type: ${zi.interactionType} | Signal: ${zi.signal || 'N/A'}`);
      lines.push(`  Confidence: ${zi.confidence}%`);
      lines.push(`  Entry: ${zi.entryPrice.toFixed(5)}`);
      lines.push(`  SL: ${zi.stopLoss.toFixed(5)} | TP: ${zi.takeProfit.toFixed(5)}`);
      lines.push(`  R:R: 1:${zi.riskReward}`);
    }

    // GLM Smart Money Engine
    if (signal.glmSmartMoney) {
      lines.push('', 'GLM SMART MONEY ENGINE', '─────────────────');
      lines.push(...this.formatGLMSmartMoneyDetailed(signal.glmSmartMoney));
    }

    // Strategy
    if (signal.strategy) {
      lines.push('', 'STRATEGY GUIDE', '─────────────────');
      lines.push(`  Title: ${signal.strategy.title}`);
      lines.push('', '  Entry Rules:');
      for (const r of signal.strategy.entryRules) lines.push(`    ✓ ${r}`);
      lines.push('', '  Exit Rules:');
      for (const r of signal.strategy.exitRules) lines.push(`    → ${r}`);
      lines.push('', '  Risk Management:');
      for (const r of signal.strategy.riskManagement) lines.push(`    🛡 ${r}`);
      lines.push('', '  Avoid:');
      for (const r of signal.strategy.avoidActions) lines.push(`    ✗ ${r}`);
    }

    // Risk Levels
    lines.push('', 'RISK LEVELS', '─────────────────');
    const riskEntriesDetailed = Object.entries(signal.riskLevels);
    for (let i = 0; i < riskEntriesDetailed.length; i++) {
      const [key, level] = riskEntriesDetailed[i];
      const mult = typeof level === 'object' && level !== null && 'multiplier' in level ? level.multiplier : level;
      const time = typeof level === 'object' && level !== null && 'time' in level ? level.time : '';
      lines.push(`  ${key}: ${mult}x  Entry Time (${time})   ← initial entry`);
    }

    // Engine Health
    if (signal.engineHealth) {
      lines.push('', 'ENGINE HEALTH', '─────────────────');
      lines.push(`  Errors Recovered: ${signal.engineHealth.errorsRecovered}`);
      lines.push(`  Fallbacks Used: ${signal.engineHealth.fallbacksUsed}`);
      lines.push(`  Recovery Rate: ${signal.engineHealth.recoveryRate}%`);
      if (signal.engineHealth.lastError) {
        lines.push(`  Last Error: ${signal.engineHealth.lastError}`);
      }
    }

    lines.push('', `═══════════════════════════════════════`);

    return lines.join('\n');
  }

  // ─── Private: MTF Formatting ──────────────────────────────────────

  private formatMTFPlain(mtf: MTFConfluence): string[] {
    const lines: string[] = [
      `  Aligned: ${mtf.aligned ? 'Yes' : 'No'} (${mtf.alignmentScore}%)`,
      `  Dominant: ${mtf.dominantTrend}`,
      `  Bullish: ${mtf.bullishCount} | Bearish: ${mtf.bearishCount} | Neutral: ${mtf.neutralCount}`,
      `  Checklist Score: ${mtf.checklistScore}%`,
    ];
    return lines;
  }

  private formatMTFEmoji(mtf: MTFConfluence): string[] {
    const lines: string[] = [
      `  ${mtf.aligned ? '✅' : '❌'} Aligned: ${mtf.alignmentScore}%`,
      `  ${mtf.dominantTrend === 'bullish' ? '🐂' : mtf.dominantTrend === 'bearish' ? '🐻' : '😐'} Dominant: ${mtf.dominantTrend}`,
      `  🟢${mtf.bullishCount} 🔴${mtf.bearishCount} ⚪${mtf.neutralCount}`,
      `  📋 MTF Checklist: ${mtf.checklistScore}%`,
    ];

    // Per-timeframe summary
    const tfEmojis: Record<string, string> = { '30s': '⚡', '45s': '🕐', '1m': '🕑', '2m': '🕒', '3m': '🕓', '5m': '🕔' };
    for (const [tf, analysis] of Object.entries(mtf.timeframeResults)) {
      const trendEmoji = analysis.trend === 'bullish' ? '📈' : analysis.trend === 'bearish' ? '📉' : '➡️';
      lines.push(`    ${tfEmojis[tf] || '📊'} ${tf}: ${trendEmoji} ${analysis.trend} (Str:${analysis.trendStrength} RSI:${analysis.rsi})`);
    }

    return lines;
  }

  // ─── Private: Zone Formatting ─────────────────────────────────────

  private formatZonePlain(zone: SupplyDemandZone): string[] {
    return [
      `  Type: ${zone.type} (${zone.direction})`,
      `  Range: ${zone.low.toFixed(5)} - ${zone.high.toFixed(5)}`,
      `  Strength: ${zone.strength} | Belief: ${zone.beliefScore}%`,
      `  Touches: ${zone.touches} | Hold Rate: ${zone.performance.holdRate}%`,
    ];
  }

  private formatZoneEmoji(zone: SupplyDemandZone): string[] {
    const dirEmoji = zone.direction === 'bullish' ? '🟢' : '🔴';
    const strengthEmoji = zone.strength === 'extreme' ? '💪' : zone.strength === 'strong' ? '🔥' : zone.strength === 'moderate' ? '⚡' : '🍃';

    return [
      `  ${dirEmoji} ${zone.type} (${zone.direction})`,
      `  Range: ${zone.low.toFixed(5)} - ${zone.high.toFixed(5)}`,
      `  ${strengthEmoji} Strength: ${zone.strength} | Belief: ${zone.beliefScore}%`,
      `  🎯 Touches: ${zone.touches} | Hold: ${zone.performance.holdRate}%`,
    ];
  }

  // ─── Private: Interaction Formatting ──────────────────────────────

  private formatInteractionPlain(interaction: ZoneInteraction): string[] {
    return [
      `  Type: ${interaction.interactionType}`,
      `  Signal: ${interaction.signal || 'N/A'}`,
      `  Confidence: ${interaction.confidence}%`,
      `  Entry: ${interaction.entryPrice.toFixed(5)}`,
      `  SL: ${interaction.stopLoss.toFixed(5)} | TP: ${interaction.takeProfit.toFixed(5)}`,
      `  R:R: 1:${interaction.riskReward}`,
    ];
  }

  private formatInteractionEmoji(interaction: ZoneInteraction): string[] {
    const signalEmoji = interaction.signal === 'BUY' ? '🟢' : interaction.signal === 'SELL' ? '🔴' : '⚪';
    const typeEmoji: Record<string, string> = {
      approach: '👀', test: '🔍', bounce: '🎯', break: '💥', flip: '🔄',
    };

    return [
      `  ${typeEmoji[interaction.interactionType] || '📊'} ${interaction.interactionType}`,
      `  ${signalEmoji} Signal: ${interaction.signal || 'N/A'} (${interaction.confidence}%)`,
      `  💰 Entry: ${interaction.entryPrice.toFixed(5)}`,
      `  🛑 SL: ${interaction.stopLoss.toFixed(5)} | 🎯 TP: ${interaction.takeProfit.toFixed(5)}`,
      `  ⚖️ R:R: 1:${interaction.riskReward}`,
    ];
  }

  // ─── Private: GLM Smart Money Formatting ─────────────────────────────

  private formatGLMSmartMoneyPlain(glm: GLMSmartMoneyResult): string[] {
    return [
      `  Structure: ${glm.labels.structure}`,
      `  Liquidity: ${glm.labels.liquidity}`,
      `  Breakout: ${glm.labels.breakout}`,
      `  Signal: ${glm.labels.signal}`,
    ];
  }

  private formatGLMSmartMoneyEmoji(glm: GLMSmartMoneyResult): string[] {
    const structureEmoji = glm.structure === 'BOS_UP' ? '🟢' : glm.structure === 'BOS_DOWN' ? '🔴' : '🟡';
    const liquidityEmoji = glm.liquidity === 'BUY_SWEEP' ? '🟢' : glm.liquidity === 'SELL_SWEEP' ? '🔴' : '⚪';
    const breakoutEmoji = glm.breakout.startsWith('CONFIRMED') ? '🚀' : '❌';
    const signalEmoji = glm.signal === 'VALID_BUY' ? '✅ 🟢' : glm.signal === 'VALID_SELL' ? '✅ 🔴' : glm.signal === 'FILTERED_NO_TRADE' ? '❌' : '⏸';

    return [
      `  ${structureEmoji} Structure: ${glm.labels.structure}`,
      `  ${liquidityEmoji} Liquidity: ${glm.labels.liquidity}`,
      `  ${breakoutEmoji} Breakout: ${glm.labels.breakout}`,
      `  ${signalEmoji} Signal: ${glm.labels.signal}`,
    ];
  }

  private formatGLMSmartMoneyDetailed(glm: GLMSmartMoneyResult): string[] {
    const lines: string[] = [
      `  Structure: ${glm.structure} — ${glm.labels.structure}`,
      `  Liquidity: ${glm.liquidity} — ${glm.labels.liquidity}`,
      `  Breakout: ${glm.breakout} — ${glm.labels.breakout}`,
      `  Final Signal: ${glm.signal} — ${glm.labels.signal}`,
      `  Price at Analysis: ${glm.price.toFixed(glm.price < 100 ? 5 : 2)}`,
    ];

    // Structure history
    if (glm.structureHistory.length > 0) {
      lines.push('', '  Structure History (last 5 bars):');
      for (const s of glm.structureHistory) {
        const emoji = s === 'BOS_UP' ? '↑' : s === 'BOS_DOWN' ? '↓' : '↔';
        lines.push(`    ${emoji} ${s}`);
      }
    }

    // Liquidity history
    if (glm.liquidityHistory.length > 0) {
      lines.push('', '  Liquidity History (last 5 bars):');
      for (const l of glm.liquidityHistory) {
        const emoji = l === 'BUY_SWEEP' ? '🟢' : l === 'SELL_SWEEP' ? '🔴' : '⚪';
        lines.push(`    ${emoji} ${l}`);
      }
    }

    return lines;
  }

  // ─── Private: Utilities ───────────────────────────────────────────

  private formatTime(entryTime: Date | string): string {
    const date = new Date(entryTime);
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
    return `${time} WAT`;
  }
}
