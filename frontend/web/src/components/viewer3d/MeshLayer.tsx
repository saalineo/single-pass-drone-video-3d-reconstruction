import { Suspense, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF, Bounds } from '@react-three/drei';
import { buildRevealScene } from './revealEffect';

const REVEAL_DURATION_S = 1.8;
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

function GltfModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  // Rebuilt per `scene` so switching meshes (or re-loading the same url after a
  // cache clear) replays the build-up instead of staying frozen at reveal=1.
  const { object, uniform } = useMemo(() => buildRevealScene(scene), [scene]);
  const elapsed = useRef(0);

  useFrame((_, delta) => {
    if (elapsed.current >= REVEAL_DURATION_S) return;
    elapsed.current = Math.min(REVEAL_DURATION_S, elapsed.current + delta);
    uniform.value = easeOutCubic(elapsed.current / REVEAL_DURATION_S);
  });

  return <primitive object={object} />;
}

export function MeshLayer({ url }: { url: string }) {
  return (
    <Suspense fallback={null}>
      {/* Bounds auto-frames the camera to the loaded model's bounding box —
          reconstructed meshes vary from a single rooftop (10s of meters) to
          a full corridor (kilometers), so a fixed camera distance is wrong
          either way. */}
      <Bounds fit clip observe margin={1.2}>
        {/* key forces a fresh mount per url, so switching models restarts the
            reveal animation instead of reusing a `useRef` that already hit 1. */}
        <GltfModel key={url} url={url} />
      </Bounds>
    </Suspense>
  );
}
