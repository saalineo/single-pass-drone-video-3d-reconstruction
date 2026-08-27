export function CoverageGapBadge({ coveragePct }: { coveragePct: number }) {
  // architect/01 NFR-5: >=90% observable-scene threshold; below it, surface loudly.
  const short = coveragePct < 90;
  return (
    <span
      title="Percent of observable scene with valid, non-occluded geometry (O-6)"
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs
        font-semibold ring-1 ${
          short
            ? 'bg-red-100 text-red-800 ring-red-300'
            : 'bg-slate-100 text-slate-700 ring-slate-300'
        }`}
    >
      {short
        ? `Coverage gap: ${coveragePct.toFixed(0)}% observed`
        : `${coveragePct.toFixed(0)}% coverage`}
    </span>
  );
}
