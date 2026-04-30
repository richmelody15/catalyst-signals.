'use client';

import { useEffect, useRef, useCallback } from 'react';
import { io, Socket } from 'socket.io-client';
import { useTradingStore } from './signal-store';
import type { Signal } from './types';

export function useSignalWebSocket() {
  const socketRef = useRef<Socket | null>(null);
  const { addSignal, setConnected, platform } = useTradingStore();

  useEffect(() => {
    const socket = io('/?XTransformPort=3003', {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 3000,
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to signal server');
      setConnected(true);
      socket.emit('subscribe', platform);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from signal server');
      setConnected(false);
    });

    socket.on('new_signal', (signal: Signal) => {
      addSignal(signal);
    });

    socket.on('heartbeat', (data: { timestamp: string; connectedClients: number; signalsGenerated: number }) => {
      // Heartbeat received, connection is alive
    });

    return () => {
      socket.emit('unsubscribe', platform);
      socket.disconnect();
    };
  }, [addSignal, setConnected, platform]);

  const requestSignal = useCallback(() => {
    socketRef.current?.emit('request_signal');
  }, []);

  const submitFeedback = useCallback((signalId: string, outcome: 'win' | 'loss') => {
    socketRef.current?.emit('signal_feedback', { signalId, outcome });
  }, []);

  return { requestSignal, submitFeedback };
}
