export function LoadingOverlay({ pct }: { pct: number | null }) {
  if (pct === null) return null;
  return (
    <div
      className="absolute inset-0 z-20 flex items-center justify-center
      bg-white/70 backdrop-blur-sm"
    >
      <div className="w-64">
        <div className="mb-2 text-center text-sm text-slate-600">
          Loading asset… {Math.round(pct)}%
        </div>
        <div className="h-2 w-full rounded-full bg-slate-200">
          <div
            className="h-2 rounded-full bg-sky-600 transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
