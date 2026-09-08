import * as THREE from 'three';

// Turns a fully-loaded model into one that assembles itself in patches — like the
// tiled Poisson meshing that actually produced it — instead of popping in whole the
// instant the download finishes. Purely a client-side presentation effect: it clones
// the loaded scene, tags every vertex with which grid cell of the model's footprint
// it belongs to, and patches each material's shader to discard fragments whose cell
// hasn't "arrived" yet. Advancing a single shared uniform from 0 -> 1 sweeps the
// whole model into view in blocky waves instead of one instant pop.

const GRID_SIZE = 14;
const CELL_STAGGER = 0.4; // fraction of a cell's slot used for in-cell jitter, keeps batches visually distinct

function computeRevealKeys(geometry: THREE.BufferGeometry, gridSize: number): Float32Array {
  geometry.computeBoundingBox();
  const bbox = geometry.boundingBox!;
  const pos = geometry.attributes.position;
  if (!pos) return new Float32Array(0);
  const count = pos.count;
  const keys = new Float32Array(count);

  const sizeX = bbox.max.x - bbox.min.x || 1;
  const sizeZ = bbox.max.z - bbox.min.z || 1;
  const maxCellSum = (gridSize - 1) * 2 || 1;

  for (let i = 0; i < count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const cx = Math.min(gridSize - 1, Math.max(0, Math.floor(((x - bbox.min.x) / sizeX) * gridSize)));
    const cz = Math.min(gridSize - 1, Math.max(0, Math.floor(((z - bbox.min.z) / sizeZ) * gridSize)));

    // Diagonal sweep order: cells nearer the min corner arrive first.
    const cellOrder = (cx + cz) / maxCellSum;
    // Small in-cell jitter (hashed, not random-per-frame) so a batch doesn't pop as
    // one hard-edged instant — but stays well inside its own slot, never bleeding
    // into the next cell's turn.
    const hash = ((cx * 928371 + cz * 12923 + i * 57) % 997) / 997;
    const jitter = (hash * CELL_STAGGER) / gridSize;

    keys[i] = Math.min(1, cellOrder + jitter);
  }
  return keys;
}

function patchMaterialForReveal(material: THREE.Material, uniform: { value: number }): THREE.Material {
  const cloned = material.clone();
  cloned.customProgramCacheKey = () => 'batch-reveal-v1';
  const prevOnBeforeCompile = cloned.onBeforeCompile;
  cloned.onBeforeCompile = (shader, renderer) => {
    prevOnBeforeCompile?.call(cloned, shader, renderer);
    shader.uniforms.uReveal = uniform;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float aRevealKey;\nvarying float vRevealKey;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvRevealKey = aRevealKey;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uReveal;\nvarying float vRevealKey;')
      .replace(
        '#include <dithering_fragment>',
        `#include <dithering_fragment>
        if (vRevealKey > uReveal) discard;
        float revealEdge = smoothstep(uReveal - 0.06, uReveal, vRevealKey);
        gl_FragColor.rgb += revealEdge * vec3(0.35, 0.85, 1.0) * 1.4;`,
      );
  };
  cloned.needsUpdate = true;
  return cloned;
}

export interface RevealHandle {
  object: THREE.Object3D;
  uniform: { value: number };
}

export function buildRevealScene(source: THREE.Object3D, gridSize = GRID_SIZE): RevealHandle {
  const object = source.clone(true);
  const uniform = { value: 0 };

  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;

    child.geometry = child.geometry.clone();
    const keys = computeRevealKeys(child.geometry, gridSize);
    child.geometry.setAttribute('aRevealKey', new THREE.BufferAttribute(keys, 1));

    if (Array.isArray(child.material)) {
      child.material = child.material.map((m) => patchMaterialForReveal(m, uniform));
    } else {
      child.material = patchMaterialForReveal(child.material, uniform);
    }
  });

  return { object, uniform };
}
