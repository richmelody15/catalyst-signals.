'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        <div className="text-center space-y-4 max-w-md">
          <div className="text-4xl">⚠️</div>
          <h2 className="text-lg font-bold text-white">CATALYST AI — Critical Error</h2>
          <p className="text-sm text-zinc-400">
            A critical error occurred. Please reload the application.
          </p>
          <button
            className="px-4 py-2 bg-emerald-400/10 text-emerald-400 rounded-lg border border-emerald-400/20 hover:bg-emerald-400/20 transition-colors text-sm"
            onClick={() => reset()}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
