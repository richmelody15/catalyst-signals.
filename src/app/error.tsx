'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('CATALYST AI Error:', error);
  }, [error]);

  const errorMessage = error?.message || 'Unknown error';
  const errorDigest = error?.digest;

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="text-center space-y-4 max-w-md">
        <div className="text-4xl">⚠️</div>
        <h2 className="text-lg font-bold text-white">CATALYST AI — Runtime Error</h2>
        <p className="text-sm text-zinc-400">
          The trading engine encountered an unexpected error. This is usually temporary and
          can be resolved by refreshing the page.
        </p>
        {errorMessage && (
          <p className="text-xs text-zinc-600 font-mono bg-zinc-900 rounded p-2 break-all">
            {errorMessage}
          </p>
        )}
        {errorDigest && (
          <p className="text-[10px] text-zinc-700">
            Digest: {errorDigest}
          </p>
        )}
        <button
          className="px-4 py-2 bg-emerald-400/10 text-emerald-400 rounded-lg border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors text-sm"
          onClick={() => reset()}
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
