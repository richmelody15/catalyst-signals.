'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { io, Socket } from 'socket.io-client';
import { useTradingStore } from './signal-store';
import type { Signal } from './types';

/**
 * WebSocket hook that connects to the signal-ws mini-service via socket.io.
 * Uses the Caddy gateway XTransformPort pattern to route to port 3003.
 *
 * The WS service pushes signals via 'new_signal' events every 8-15 seconds.
 * When a signal is received, it's normalized and added to the Zustand store.
 */
export function useSignalWebSocket() {
  const socketRef = useRef<Socket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const { addSignal, setConnected, platform } = useTradingStore();
  const [backendAvailable, setBackendAvailable] = useState(false);

  // Connect to signal-ws mini-service via socket.io through Caddy gateway
  useEffect(() => {
    if (typeof window === 'undefined') return; // SSR guard

    let cancelled = false;

    function connect() {
      if (cancelled) return;

      try {
        // Use socket.io with XTransformPort for Caddy gateway routing
        const socket = io('/?XTransformPort=3003', {
          transports: ['websocket', 'polling'],
          reconnection: true,
          reconnectionAttempts: 20,
          reconnectionDelay: 3000,
          reconnectionDelayMax: 10000,
          timeout: 10000,
        });

        socket.on('connect', () => {
          if (cancelled) return;
          console.log('[WS] Connected to signal-ws service via socket.io');
          setConnected(true);
          setBackendAvailable(true);

          // Subscribe to current platform
          socket.emit('subscribe', platform);
        });

        socket.on('connected', (data) => {
          if (cancelled) return;
          console.log('[WS] Server welcome:', data);
        });

        socket.on('new_signal', (data: Record<string, unknown>) => {
          if (cancelled) return;
          try {
            // The signal from WS service may have slightly different shape
            // The store's normalizeSignal handles all edge cases
            addSignal(data as unknown as Signal);
          } catch (e) {
            console.warn('[WS] Failed to add signal:', e);
          }
        });

        socket.on('platform_signal', (data: Record<string, unknown>) => {
          if (cancelled) return;
          try {
            addSignal(data as unknown as Signal);
          } catch (e) {
            console.warn('[WS] Failed to add platform signal:', e);
          }
        });

        socket.on('heartbeat', (data) => {
          // Connection alive — could update UI with client count etc.
        });

        socket.on('feedback_recorded', (data) => {
          console.log('[WS] Feedback recorded:', data);
        });

        socket.on('disconnect', (reason) => {
          if (cancelled) return;
          console.log('[WS] Disconnected:', reason);
          setConnected(false);
          setBackendAvailable(false);
        });

        socket.on('connect_error', (error) => {
          if (cancelled) return;
          console.warn('[WS] Connection error:', error.message);
          setConnected(false);
          setBackendAvailable(false);
        });

        socketRef.current = socket;
      } catch (err) {
        console.warn('[WS] Failed to initialize socket.io:', err);
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
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
      }
    };
  }, [addSignal, setConnected, platform]);

  // Request signal from WS service
  const requestSignal = useCallback(() => {
    if (socketRef.current && socketRef.current.connected) {
      socketRef.current.emit('request_signal');
    }
  }, []);

  // Submit feedback to WS service
  const submitFeedback = useCallback((signalId: string, outcome: 'win' | 'loss') => {
    if (socketRef.current && socketRef.current.connected) {
      socketRef.current.emit('signal_feedback', { signalId, outcome });
    }
  }, []);

  return { requestSignal, submitFeedback, backendAvailable };
}
