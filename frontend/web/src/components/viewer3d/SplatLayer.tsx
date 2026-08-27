import { useEffect, useRef } from 'react';
import { useThree } from '@react-three/fiber';
import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d';

export function SplatLayer({
  url,
  onProgress,
}: {
  url: string;
  onProgress?: (pct: number) => void;
}) {
  const { scene, camera, gl } = useThree();
  const viewerRef = useRef<GaussianSplats3D.DropInViewer | null>(null);

  useEffect(() => {
    const viewer = new GaussianSplats3D.DropInViewer({
      selfDrivenMode: false, // r3f drives the render loop; this must not fight it
      renderer: gl,
      camera,
    });
    viewerRef.current = viewer;
    scene.add(viewer);

    viewer
      .addSplatScene(url, {
        splatAlphaRemovalThreshold: 5, // drop near-transparent splats, cuts VRAM
        progressiveLoad: true,
        onProgress: (pct: number) => onProgress?.(pct * 100),
      })
      .catch((err: Error) => console.error('splat scene load failed', err));

    return () => {
      scene.remove(viewer);
      viewer.dispose();
    };
  }, [url, scene, camera, gl, onProgress]);

  return null;
}
