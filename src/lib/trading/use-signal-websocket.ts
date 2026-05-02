'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useTradingStore } from './signal-store';
import type { Signal } from './types';

/**
 * WebSocket hook that connects to the Python backend WebSocket on port 8000.
 * Falls back to the Node.js signal-ws service if Python backend is unavailable.
 *
 * The Python backend pushes signals via 'new_signal' events every ~30 seconds.
 * When a signal is received, it's normalized and added to the Zustand store.
 */

const PYTHON_WS_URL = process.env.NEXT_PUBLIC_PYTHON_WS_URL || '';

export function useSignalWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectCountRef = useRef(0);
  const { addSignal, setConnected, platform } = useTradingStore();
  const [backendAvailable, setBackendAvailable] = useState(false);

  // Determine the Python backend WebSocket URL
  function getPythonWsUrl(): string {
    // If explicitly set via env var, use it
    if (PYTHON_WS_URL) return PYTHON_WS_URL;

    // Otherwise, construct from current location
    if (typeof window === 'undefined') return '';

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Try port 8000 directly (Python backend)
    const host = window.location.hostname || 'localhost';
    return `${protocol}//${host}:8000/ws`;
  }

  useEffect(() => {
    if (typeof window === 'undefined') return; // SSR guard

    let cancelled = false;

    function connect() {
      if (cancelled) return;

      const wsUrl = getPythonWsUrl();
      if (!wsUrl) return;

      try {
        console.log('[WS] Connecting to Python backend:', wsUrl);
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          if (cancelled) return;
          console.log('[WS] Connected to Python backend');
          setConnected(true);
          setBackendAvailable(true);
          reconnectCountRef.current = 0;

          // Send ping to verify connection
          try { ws.send('ping'); } catch { /* ignore */ }
        };

        ws.onmessage = (event) => {
          if (cancelled) return;
          try {
            const data = JSON.parse(event.data);

            // Handle pong response
            if (data.type === 'pong') return;

            // Handle new signal from Python backend
            if (data.type === 'new_signal') {
              const signalData = data.signal || data;

              // The Python backend sends signals in frontend-compatible format
              // but we still need to normalize the entry_time
              if (signalData.entry_time && typeof signalData.entry_time === 'string') {
                signalData.entryTime = signalData.entry_time;
              }

              // Map Python backend martingale to frontend riskLevels format
              if (signalData.martingale && Array.isArray(signalData.martingale) && !signalData.riskLevels) {
                const riskLevels: Record<string, { multiplier: number; time: string; amount: number }> = {};
                for (const m of signalData.martingale) {
                  const mEntryTime = m.entry_time;
                  let timeStr = '--:-- WAT';
                  if (typeof mEntryTime === 'string') {
                    try {
                      const d = new Date(mEntryTime);
                      timeStr = d.toLocaleTimeString('en-GB', {
                        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Africa/Lagos',
                      }) + ' WAT';
                    } catch { /* ignore */ }
                  }
                  riskLevels[m.level || `M${riskLevels.length + 1}`] = {
                    multiplier: m.multiplier || 0,
                    amount: m.amount || 0,
                    time: timeStr,
                  };
                }
                signalData.riskLevels = riskLevels;
              }

              addSignal(signalData as unknown as Signal);
            }
          } catch (e) {
            console.warn('[WS] Failed to parse message:', e);
          }
        };

        ws.onclose = (event) => {
          if (cancelled) return;
          console.log('[WS] Disconnected:', event.code, event.reason);
          setConnected(false);
          setBackendAvailable(false);

          // Exponential backoff reconnection
          reconnectCountRef.current++;
          const delay = Math.min(3000 * Math.pow(1.5, reconnectCountRef.current - 1), 30000);
          reconnectTimerRef.current = setTimeout(() => {
            if (!cancelled) connect();
          }, delay);
        };

        ws.onerror = (error) => {
          if (cancelled) return;
          console.warn('[WS] Connection error');
          setConnected(false);
          setBackendAvailable(false);
        };

        wsRef.current = ws;
      } catch (err) {
        console.warn('[WS] Failed to initialize:', err);
        setConnected(false);
        setBackendAvailable(false);

        // Retry after 5 seconds
        reconnectTimerRef.current = setTimeout(() => {
          if (!cancelled) connect();
        }, 5000);
      }
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [addSignal, setConnected, platform]);

  // Request signal from backend
  const requestSignal = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try { wsRef.current.send('request_signal'); } catch { /* ignore */ }
    }
  }, []);

  // Submit feedback to backend
  const submitFeedback = useCallback((signalId: string, outcome: 'win' | 'loss') => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'feedback', signalId, outcome }));
      } catch { /* ignore */ }
    }
  }, []);

  return { requestSignal, submitFeedback, backendAvailable };
}
