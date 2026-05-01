'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useTradingStore } from './signal-store';
import type { Signal } from './types';

// Lazy-load socket.io only when needed to avoid SSR issues
let _io: typeof import('socket.io-client').io | null = null;
async function getIO() {
  if (!_io) {
    try {
      const mod = await import('socket.io-client');
      _io = mod.io;
    } catch {
      // socket.io-client not available
      return null;
    }
  }
  return _io;
}

export function useSignalWebSocket() {
  const socketRef = useRef<ReturnType<typeof import('socket.io-client').io> | null>(null);
  const { addSignal, setConnected, platform } = useTradingStore();

  useEffect(() => {
    let cancelled = false;

    async function connect() {
      const ioFn = await getIO();
      if (cancelled || !ioFn) return;

      try {
        const socket = ioFn('/?XTransformPort=3003', {
          transports: ['websocket', 'polling'],
          reconnection: true,
          reconnectionAttempts: 5,
          reconnectionDelay: 5000,
          timeout: 10000,
        });

        socketRef.current = socket;

        socket.on('connect', () => {
          if (!cancelled) {
            console.log('Connected to signal server');
            setConnected(true);
            socket.emit('subscribe', platform);
          }
        });

        socket.on('disconnect', () => {
          if (!cancelled) {
            console.log('Disconnected from signal server');
            setConnected(false);
          }
        });

        socket.on('connect_error', (err: Error) => {
          if (!cancelled) {
            console.warn('WebSocket connection error (non-fatal):', err.message);
            setConnected(false);
          }
        });

        socket.on('new_signal', (signal: Signal) => {
          if (!cancelled) {
            addSignal(signal);
          }
        });

        socket.on('heartbeat', () => {
          // Heartbeat received, connection is alive
        });
      } catch (err) {
        console.warn('Failed to initialize WebSocket (non-fatal):', err);
      }
    }

    connect();

    return () => {
      cancelled = true;
      try {
        socketRef.current?.emit('unsubscribe', platform);
        socketRef.current?.disconnect();
      } catch {
        // Ignore cleanup errors
      }
      socketRef.current = null;
    };
  }, [addSignal, setConnected, platform]);

  const requestSignal = useCallback(() => {
    try {
      socketRef.current?.emit('request_signal');
    } catch {
      // WebSocket not available
    }
  }, []);

  const submitFeedback = useCallback((signalId: string, outcome: 'win' | 'loss') => {
    try {
      socketRef.current?.emit('signal_feedback', { signalId, outcome });
    } catch {
      // WebSocket not available
    }
  }, []);

  return { requestSignal, submitFeedback };
}
