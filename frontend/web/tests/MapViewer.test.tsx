import { downsample } from '@/components/map/TrajectoryLayer';
import type { PoseTrailFeature } from '@/types/liveFeed';

// Cesium/resium's <Viewer> requires a real WebGL context, which jsdom does not
// provide (mirrors day-25's Viewer3D testing constraint) — coverage here
// targets the pure trajectory-downsampling logic MapViewer's rendering
// depends on; the map render itself is manual/visual QA.

function fixturePoint(i: number): PoseTrailFeature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-122.4 + i * 0.0001, 37.7, 50] },
    properties: { timestamp: new Date(i * 1000).toISOString(), headingDeg: 0, quality: 'draft' },
  };
}

test('passes short tracks through unchanged', () => {
  const track = Array.from({ length: 10 }, (_, i) => fixturePoint(i));
  expect(downsample(track)).toEqual(track);
});

test('downsamples long tracks while always keeping the latest point', () => {
  const track = Array.from({ length: 5000 }, (_, i) => fixturePoint(i));
  const result = downsample(track);
  expect(result.length).toBeLessThanOrEqual(501);
  expect(result[result.length - 1]).toEqual(track[track.length - 1]);
});
