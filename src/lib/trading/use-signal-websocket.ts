'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useTradingStore } from './signal-store';
import type { Signal } from './types';

// Backend URL configuration
const PYTHON_BACKEND_WS = process.env.NEXT_PUBLIC_PYTHON_BACKEND_WS || 'ws://localhost:8000/ws';
const PYTHON_BACKEND_HTTP = process.env.NEXT_PUBLIC_PYTHON_BACKEND_HTTP || 'http://localhost:8000';

/**
 * WebSocket hook that connects to the Python FastAPI backend.
 * Supports both native WebSocket (for Python backend) and socket.io fallback.
 *
 * The Python backend pushes signals via native WebSocket at /ws endpoint.
 * When a signal is received, it's normalized and added to the Zustand store.
 */
export function useSignalWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const { addSignal, setConnected, platform } = useTradingStore();
  const [backendAvailable, setBackendAvailable] = useState(false);

  // Connect to Python backend native WebSocket
  useEffect(() => {
    if (typeof window === 'undefined') return; // SSR guard

    let cancelled = false;

    function connect() {
      if (cancelled) return;

      try {
        const ws = new WebSocket(PYTHON_BACKEND_WS);

        ws.onopen = () => {
          if (cancelled) return;
          console.log('[WS] Connected to Python backend');
          setConnected(true);
          setBackendAvailable(true);
        };

        ws.onmessage = (event) => {
          if (cancelled) return;
          try {
            const data = JSON.parse(event.data);

            // Handle new_signal event from Python backend
            if (data.type === 'new_signal' && data.signal) {
              addSignal(data.signal as Signal);
            }

            // Handle signals batch event
            if (data.type === 'signals' && Array.isArray(data.signals)) {
              for (const signal of data.signals) {
                try {
                  addSignal(signal as Signal);
                } catch (e) {
                  console.warn('[WS] Failed to add signal:', e);
                }
              }
            }

            // Handle pong
            if (data.type === 'pong') {
              // Connection alive
            }
          } catch (e) {
            console.warn('[WS] Failed to parse message:', e);
          }
        };

        ws.onclose = () => {
          if (cancelled) return;
          console.log('[WS] Disconnected from Python backend');
          setConnected(false);
          setBackendAvailable(false);

          // Reconnect after 3 seconds
          reconnectTimerRef.current = setTimeout(() => {
            if (!cancelled) connect();
          }, 3000);
        };

        ws.onerror = (error) => {
          if (cancelled) return;
          console.warn('[WS] Connection error:', error);
          setConnected(false);
          setBackendAvailable(false);
        };

        wsRef.current = ws;
      } catch (err) {
        console.warn('[WS] Failed to initialize WebSocket:', err);
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

  // Request signal from Python backend
  const requestSignal = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'request_signal' }));
    }
  }, []);

  // Submit feedback to Python backend
  const submitFeedback = useCallback((signalId: string, outcome: 'win' | 'loss') => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'feedback', signalId, outcome }));
    }

    // Also send to Python backend REST API
    fetch(`${PYTHON_BACKEND_HTTP}/api/signals/${signalId}/close?outcome=${outcome}`, {
      method: 'POST',
    }).catch(() => {
      // Silently fail — backend may not be available
    });
  }, []);

  return { requestSignal, submitFeedback, backendAvailable };
}
