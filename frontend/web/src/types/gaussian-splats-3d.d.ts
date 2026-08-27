// @mkkellogg/gaussian-splats-3d ships no TypeScript declarations; this is a
// minimal ambient surface covering the DropInViewer API SplatLayer.tsx uses.
declare module '@mkkellogg/gaussian-splats-3d' {
  import type { Camera, Object3D, WebGLRenderer } from 'three';

  export interface DropInViewerOptions {
    selfDrivenMode?: boolean;
    renderer?: WebGLRenderer;
    camera?: Camera;
  }

  export interface AddSplatSceneOptions {
    splatAlphaRemovalThreshold?: number;
    progressiveLoad?: boolean;
    onProgress?: (pct: number) => void;
  }

  export class DropInViewer extends Object3D {
    constructor(options?: DropInViewerOptions);
    addSplatScene(url: string, options?: AddSplatSceneOptions): Promise<void>;
    dispose(): void;
  }
}
