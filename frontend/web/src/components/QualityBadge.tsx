import type { ProductQuality } from '@/types/product';

export function QualityBadge({ quality }: { quality: ProductQuality }) {
  if (quality === 'draft') {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-amber-100
        px-2.5 py-0.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-300"
      >
        DRAFT — fast-track, not survey-grade
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-emerald-100
      px-2.5 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-300"
    >
      SURVEY — final product
    </span>
  );
}
