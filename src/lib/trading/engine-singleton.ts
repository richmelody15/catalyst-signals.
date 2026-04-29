// Singleton engine instances shared across API routes
import { SignalGenerator } from './signal-generator';
import { MarketSimulator } from './signal-simulator';
import { SelfLearningEngine } from './self-learning';

export const signalGenerator = new SignalGenerator();
export const marketSimulator = new MarketSimulator();
export const learningEngine = new SelfLearningEngine();

// Initialize simulator
let initialized = false;
export function ensureInitialized() {
  if (!initialized) {
    marketSimulator.initialize();
    initialized = true;
  }
}
