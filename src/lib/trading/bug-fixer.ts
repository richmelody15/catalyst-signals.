// CATALYST AI - Bug Fixer Engine
// Auto-fix decorator pattern, SafeExecution context, and error recording
// Converted from Python: @bug_fixer.auto_fix_decorator, SafeExecution, bug_fixer.record_error

import type { BugFixerConfig, BugFixerStats, ErrorRecord } from './types';

/**
 * BugFixer — Resilience layer for the trading engine.
 *
 * Provides:
 * - `autoFixDecorator` — wraps a function with retry + fallback logic
 * - `SafeExecution` — async context manager for risky code blocks
 * - `recordError` — manual error recording for catch blocks
 * - `getStats` — health statistics for dashboard display
 */
export class BugFixer {
  private errors: ErrorRecord[] = [];
  private maxErrorHistory = 500;
  private errorCounter = 0;

  // ─── Auto-Fix Decorator ──────────────────────────────────────────
  /**
   * Wraps a function with automatic retry and fallback behavior.
   *
   * TypeScript equivalent of Python's @bug_fixer.auto_fix_decorator(fallback_value=[], retry_count=3)
   *
   * Usage:
   * ```ts
   * const safeGetData = bugFixer.autoFixDecorator(
   *   async (symbol: string, tf: string) => fetchMarketData(symbol, tf),
   *   { fallbackValue: [], retryCount: 3, module: 'market', function: 'getData' }
   * );
   * const data = await safeGetData('EURUSD-OTC', '1m');
   * ```
   */
  autoFixDecorator<TArgs extends unknown[], TReturn>(
    fn: (...args: TArgs) => Promise<TReturn>,
    config: Partial<BugFixerConfig> & { module: string; function: string }
  ): (...args: TArgs) => Promise<TReturn> {
    const fullConfig: BugFixerConfig = {
      fallbackValue: config.fallbackValue ?? null,
      retryCount: config.retryCount ?? 3,
      retryDelay: config.retryDelay ?? 500,
      module: config.module,
      function: config.function,
    };

    return async (...args: TArgs): Promise<TReturn> => {
      let lastError: Error | null = null;

      for (let attempt = 0; attempt < fullConfig.retryCount; attempt++) {
        try {
          const result = await fn(...args);
          return result;
        } catch (err) {
          lastError = err instanceof Error ? err : new Error(String(err));

          // Record the error
          this.recordErrorInternal(
            lastError,
            fullConfig.module,
            fullConfig.function,
            attempt,
            attempt < fullConfig.retryCount - 1, // recovered if we'll retry
            false // fallback not used yet
          );

          // Wait before retrying (exponential backoff)
          if (attempt < fullConfig.retryCount - 1) {
            const delay = fullConfig.retryDelay * Math.pow(2, attempt);
            await this.sleep(delay);
          }
        }
      }

      // All retries failed — use fallback
      if (lastError) {
        this.recordErrorInternal(
          lastError,
          fullConfig.module,
          fullConfig.function,
          fullConfig.retryCount,
          false, // not recovered
          true   // fallback used
        );
      }

      return fullConfig.fallbackValue as TReturn;
    };
  }

  /**
   * Synchronous version of autoFixDecorator for non-async functions.
   */
  autoFixDecoratorSync<TArgs extends unknown[], TReturn>(
    fn: (...args: TArgs) => TReturn,
    config: Partial<BugFixerConfig> & { module: string; function: string }
  ): (...args: TArgs) => TReturn {
    const fullConfig: BugFixerConfig = {
      fallbackValue: config.fallbackValue ?? null,
      retryCount: config.retryCount ?? 3,
      retryDelay: 0, // no delay for sync
      module: config.module,
      function: config.function,
    };

    return (...args: TArgs): TReturn => {
      let lastError: Error | null = null;

      for (let attempt = 0; attempt < fullConfig.retryCount; attempt++) {
        try {
          return fn(...args);
        } catch (err) {
          lastError = err instanceof Error ? err : new Error(String(err));
          this.recordErrorInternal(lastError, fullConfig.module, fullConfig.function, attempt, false, false);
        }
      }

      // All retries failed — use fallback
      if (lastError) {
        this.recordErrorInternal(lastError, fullConfig.module, fullConfig.function, fullConfig.retryCount, false, true);
      }

      return fullConfig.fallbackValue as TReturn;
    };
  }

  // ─── Safe Execution Context ──────────────────────────────────────
  /**
   * Creates a safe execution wrapper for risky code blocks.
   *
   * TypeScript equivalent of Python's `async with SafeExecution(bug_fixer, "module"):`
   *
   * Usage:
   * ```ts
   * const result = await bugFixer.safeExecution('signal_generation', async () => {
   *   // Risky operation
   *   return generateSignal(data);
   * });
   * ```
   */
  async safeExecution<TReturn>(
    moduleName: string,
    fn: () => Promise<TReturn>,
    fallbackValue?: TReturn
  ): Promise<TReturn | null> {
    try {
      return await fn();
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      this.recordErrorInternal(error, moduleName, 'safeExecution', 0, false, fallbackValue !== undefined);

      if (fallbackValue !== undefined) {
        return fallbackValue;
      }
      return null;
    }
  }

  // ─── Manual Error Recording ──────────────────────────────────────
  /**
   * Manually record an error from a catch block.
   *
   * TypeScript equivalent of Python's `await bug_fixer.record_error(e, module="trading", function="analyze")`
   */
  recordError(
    error: Error | unknown,
    options: { module: string; function: string; recovered?: boolean; fallbackUsed?: boolean }
  ): void {
    const err = error instanceof Error ? error : new Error(String(error));
    this.recordErrorInternal(
      err,
      options.module,
      options.function,
      0,
      options.recovered ?? false,
      options.fallbackUsed ?? false
    );
  }

  // ─── Statistics ──────────────────────────────────────────────────
  /**
   * Get bug fixer statistics for health dashboard display.
   */
  getStats(): BugFixerStats {
    const totalErrors = this.errors.length;
    const recoveredErrors = this.errors.filter(e => e.recovered).length;
    const fallbackUsed = this.errors.filter(e => e.fallbackUsed).length;
    const unrecoveredErrors = totalErrors - recoveredErrors - fallbackUsed;

    const errorsByModule: Record<string, number> = {};
    for (const err of this.errors) {
      errorsByModule[err.module] = (errorsByModule[err.module] || 0) + 1;
    }

    return {
      totalErrors,
      recoveredErrors,
      fallbackUsed,
      unrecoveredErrors: Math.max(0, unrecoveredErrors),
      recoveryRate: totalErrors > 0 ? (recoveredErrors / totalErrors) * 100 : 100,
      errorsByModule,
      recentErrors: this.errors.slice(-20),
    };
  }

  /**
   * Get engine health snapshot for inclusion in signals.
   */
  getEngineHealth(): { errorsRecovered: number; fallbacksUsed: number; recoveryRate: number; lastError: string | null } {
    const stats = this.getStats();
    const lastError = this.errors.length > 0 ? this.errors[this.errors.length - 1].error : null;
    return {
      errorsRecovered: stats.recoveredErrors,
      fallbacksUsed: stats.fallbackUsed,
      recoveryRate: +stats.recoveryRate.toFixed(1),
      lastError,
    };
  }

  /**
   * Clear error history (for testing or periodic cleanup).
   */
  clearErrors(): void {
    this.errors = [];
    this.errorCounter = 0;
  }

  // ─── Internal ────────────────────────────────────────────────────
  private recordErrorInternal(
    error: Error,
    module: string,
    functionName: string,
    retryCount: number,
    recovered: boolean,
    fallbackUsed: boolean
  ): void {
    this.errorCounter++;
    const record: ErrorRecord = {
      id: `ERR-${Date.now()}-${this.errorCounter}`,
      error: error.message || String(error),
      module,
      function: functionName,
      timestamp: new Date().toISOString(),
      retryCount,
      recovered,
      fallbackUsed,
    };

    this.errors.push(record);

    // Trim history if too long
    if (this.errors.length > this.maxErrorHistory) {
      this.errors = this.errors.slice(-this.maxErrorHistory);
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Singleton instance — shared across all trading engine modules
export const bugFixer = new BugFixer();
