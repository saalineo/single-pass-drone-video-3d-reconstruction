import { Suspense } from 'react';
import { useGLTF, Bounds } from '@react-three/drei';

function GltfModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

export function MeshLayer({ url }: { url: string }) {
  return (
    <Suspense fallback={null}>
      {/* Bounds auto-frames the camera to the loaded model's bounding box —
          reconstructed meshes vary from a single rooftop (10s of meters) to
          a full corridor (kilometers), so a fixed camera distance is wrong
          either way. */}
      <Bounds fit clip observe margin={1.2}>
        <GltfModel url={url} />
      </Bounds>
    </Suspense>
  );
}
