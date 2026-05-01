'use client';

import React from 'react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error, errorInfo: null };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const errorMessage = this.state.error?.message || 'Unknown error';
      const componentStack = this.state.errorInfo?.componentStack || '';

      return (
        <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
          <div className="text-center space-y-4 max-w-lg">
            <div className="text-4xl">⚠️</div>
            <h2 className="text-lg font-bold text-white">CATALYST AI — Rendering Error</h2>
            <p className="text-sm text-zinc-400">
              The trading engine encountered an unexpected error during rendering.
              This is usually caused by incomplete signal data and can be resolved by refreshing.
            </p>
            <div className="bg-zinc-900 rounded-lg p-3 text-left max-h-40 overflow-auto">
              <p className="text-xs text-red-400 font-mono break-all">{errorMessage}</p>
              {componentStack && (
                <pre className="text-[10px] text-zinc-600 mt-2 whitespace-pre-wrap">{componentStack.slice(0, 500)}</pre>
              )}
            </div>
            <button
              className="px-4 py-2 bg-emerald-400/10 text-emerald-400 rounded-lg border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors text-sm"
              onClick={() => {
                this.setState({ hasError: false, error: null, errorInfo: null });
                window.location.reload();
              }}
            >
              Reload Dashboard
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
