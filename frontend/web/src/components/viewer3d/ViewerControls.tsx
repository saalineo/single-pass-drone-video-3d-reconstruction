import type { ProductKind } from '@/types/product';

export function ViewerControls({
  mode,
  available,
  onChange,
}: {
  mode: ProductKind;
  available: ProductKind[];
  onChange: (kind: ProductKind) => void;
}) {
  const LABEL: Partial<Record<ProductKind, string>> = {
    mesh_glb: 'Textured Mesh',
    gaussian_splat: 'Gaussian Splat',
  };
  return (
    <div
      className="absolute left-4 top-4 z-10 flex gap-2 rounded-md bg-white/90
      p-1 shadow"
    >
      {available.map((kind) => (
        <button
          key={kind}
          onClick={() => onChange(kind)}
          className={`rounded px-3 py-1 text-sm ${
            mode === kind ? 'bg-sky-600 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          {LABEL[kind] ?? kind}
        </button>
      ))}
    </div>
  );
}
