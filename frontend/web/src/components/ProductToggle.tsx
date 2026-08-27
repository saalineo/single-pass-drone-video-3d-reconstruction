import type { Product, ProductQuality } from '@/types/product';

export function ProductToggle({
  variants,
  selected,
  onChange,
}: {
  variants: Product[];
  selected: ProductQuality;
  onChange: (q: ProductQuality) => void;
}) {
  const qualities = [...new Set(variants.map((v) => v.quality))];
  if (qualities.length < 2) return null; // nothing to toggle; only one tier exists
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-500">Viewing:</span>
      {qualities.map((q) => (
        <button
          key={q}
          onClick={() => onChange(q)}
          className={`rounded px-2 py-1 ${
            selected === q ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600'
          }`}
        >
          {q === 'draft' ? 'Draft (fast-track)' : 'Survey (final)'}
        </button>
      ))}
    </div>
  );
}
