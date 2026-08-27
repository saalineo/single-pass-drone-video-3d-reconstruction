import { Entity, PolygonGraphics } from 'resium';
import { Cartesian3, Color, PolygonHierarchy } from 'cesium';

function toDegreesArray(polygon: GeoJSON.Polygon): number[] {
  const ring = polygon.coordinates[0] ?? [];
  return ring.flatMap((position: GeoJSON.Position): [number, number] => {
    const lon = position[0] ?? 0;
    const lat = position[1] ?? 0;
    // GeoJSON is [lon, lat]; catches an accidental fromDegrees(lat, lon) swap
    // early instead of a silently-garbled polygon on the wrong continent.
    if (import.meta.env.DEV) {
      console.assert(
        Math.abs(lon) <= 180 && Math.abs(lat) <= 90,
        `AoiLayer: suspected lon/lat axis-order swap in coordinate [${lon}, ${lat}]`,
      );
    }
    return [lon, lat];
  });
}

export function AoiLayer({ aoi }: { aoi: GeoJSON.Polygon }) {
  const hierarchy = new PolygonHierarchy(Cartesian3.fromDegreesArray(toDegreesArray(aoi)));
  return (
    <Entity name="Area of Interest">
      <PolygonGraphics
        hierarchy={hierarchy}
        material={Color.CYAN.withAlpha(0.15)}
        outline
        outlineColor={Color.CYAN}
        outlineWidth={2}
      />
    </Entity>
  );
}
