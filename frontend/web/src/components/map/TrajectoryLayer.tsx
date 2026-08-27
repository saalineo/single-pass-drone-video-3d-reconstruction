import { Entity, PolylineGraphics, PointGraphics } from 'resium';
import { Cartesian3, Color, PolylineDashMaterialProperty } from 'cesium';
import type { PoseTrailFeature } from '@/types/liveFeed';

// A long flight at 10 Hz pose updates (architect/07 §3) accumulates tens of
// thousands of points per hour; beyond this many, only render the most
// recent tail plus a downsampled history so Cesium isn't re-fed the full
// array every frame.
const MAX_RENDERED_POINTS = 500;

export function downsample(track: PoseTrailFeature[]): PoseTrailFeature[] {
  if (track.length <= MAX_RENDERED_POINTS) return track;
  const stride = Math.ceil(track.length / MAX_RENDERED_POINTS);
  const sampled = track.filter((_, i) => i % stride === 0);
  const last = track[track.length - 1];
  if (last && sampled[sampled.length - 1] !== last) sampled.push(last);
  return sampled;
}

export function TrajectoryLayer({
  track,
  isLive,
}: {
  track: PoseTrailFeature[];
  isLive: boolean;
}) {
  if (track.length === 0) return null;
  const rendered = downsample(track);
  const positions = rendered.map((f) => Cartesian3.fromDegrees(...f.geometry.coordinates));
  return (
    <>
      <Entity name="Flight Trajectory">
        <PolylineGraphics
          positions={positions}
          width={3}
          material={
            isLive
              ? new PolylineDashMaterialProperty({ color: Color.ORANGE })
              : Color.LIME
          }
        />
      </Entity>
      {isLive && (
        <Entity name="Current Position" position={positions[positions.length - 1]}>
          <PointGraphics pixelSize={10} color={Color.ORANGE} />
        </Entity>
      )}
    </>
  );
}
