import { render, screen } from '@testing-library/react';
import { Viewer3D } from '@/components/Viewer3D';
import type { Product } from '@/types/product';

// Full GPU-path testing (mesh/splat render) is brittle in jsdom without a real
// WebGL context — per day-25's pitfalls, keep unit coverage to the
// non-Three.js logic (product filtering) and rely on manual/visual QA for the
// actual render.
test('shows an empty state when no mesh or splat product exists', () => {
  const products: Product[] = [
    {
      id: 'p1',
      missionId: 'm1',
      kind: 'orthomosaic',
      format: 'geotiff',
      url: '/fixtures/ortho.tif',
      crs: 'EPSG:32633',
      bbox: [0, 0, 0, 1, 1, 1],
      checksum: 'sha256:abc',
      quality: 'survey',
      provenanceRef: null,
      sizeBytes: 1024,
    },
  ];
  render(<Viewer3D products={products} />);
  expect(
    screen.getByText(/no mesh or splat product published yet/i),
  ).toBeInTheDocument();
});
