import { useMemo, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { Product, ProductKind } from '@/types/product';
import { MeshLayer } from './viewer3d/MeshLayer';
import { SplatLayer } from './viewer3d/SplatLayer';
import { ViewerControls } from './viewer3d/ViewerControls';
import { LoadingOverlay } from './viewer3d/LoadingOverlay';

const RENDERABLE: ProductKind[] = ['mesh_glb', 'gaussian_splat'];

export function Viewer3D({ products }: { products: Product[] }) {
  const renderable = useMemo(
    () => products.filter((p) => RENDERABLE.includes(p.kind)),
    [products],
  );
  const [mode, setMode] = useState<ProductKind | null>(renderable[0]?.kind ?? null);
  const [loadPct, setLoadPct] = useState<number | null>(0);
  const active = renderable.find((p) => p.kind === mode);

  if (!active) {
    return (
      <div className="flex h-full items-center justify-center text-slate-400">
        No mesh or splat product published yet for this mission.
      </div>
    );
  }

  return (
    <div className="relative h-[560px] w-full overflow-hidden rounded-lg bg-slate-900">
      <ViewerControls
        mode={active.kind}
        available={renderable.map((p) => p.kind)}
        onChange={(kind) => {
          setMode(kind);
          setLoadPct(0);
        }}
      />
      <LoadingOverlay pct={loadPct !== null && loadPct < 100 ? loadPct : null} />
      <Canvas camera={{ position: [10, 10, 10], fov: 50, near: 0.1, far: 5000 }}>
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 10, 5]} intensity={1.2} />
        {active.kind === 'mesh_glb' && <MeshLayer url={active.url} />}
        {active.kind === 'gaussian_splat' && (
          <SplatLayer url={active.url} onProgress={setLoadPct} />
        )}
        <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
      </Canvas>
    </div>
  );
}
