import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Viewer } from 'resium';
import type { Mission } from '@/types/mission';
import type { Product } from '@/types/product';
import type { PoseTrailFeature } from '@/types/liveFeed';
import { useLiveTrajectory } from '@/hooks/useLiveTrajectory';
import { AoiLayer } from './map/AoiLayer';
import { TrajectoryLayer } from './map/TrajectoryLayer';
import { CoverageRasterLayer } from './map/CoverageRasterLayer';
import { LayerToggle, type LayerVisibility } from './map/LayerToggle';

interface StaticTrajectoryGeoJson {
  type: 'FeatureCollection';
  features: PoseTrailFeature[];
}

export function MapViewer({ mission, products }: { mission: Mission; products: Product[] }) {
  const {
    track: liveTrack,
    linkHealth,
    connState,
  } = useLiveTrajectory(mission.id, mission.status);
  const [visibility, setVisibility] = useState<LayerVisibility>({
    aoi: true,
    trajectory: true,
    coverage: false,
  });

  const trajectoryProduct = products.find((p) => p.kind === 'trajectory');
  const coverageProduct = products.find((p) => p.kind === 'confidence_raster');
  const isLive = mission.status === 'in_flight';

  // Static missions render the committed O-5 GeoJSON track; normalize into
  // the same PoseTrailFeature shape the live socket produces so
  // TrajectoryLayer only ever has one input type to handle.
  const { data: staticGeoJson } = useQuery({
    queryKey: ['trajectory', trajectoryProduct?.id],
    queryFn: () =>
      fetch(trajectoryProduct!.url).then((r) => r.json() as Promise<StaticTrajectoryGeoJson>),
    enabled: !isLive && !!trajectoryProduct,
  });
  const staticTrack = staticGeoJson?.features ?? [];
  const track = isLive ? liveTrack : staticTrack;

  return (
    <div className="relative h-[560px] w-full overflow-hidden rounded-lg">
      {isLive && (
        <div
          className="absolute right-4 top-4 z-10 rounded-md bg-white/90 px-3 py-1.5
          text-xs shadow"
        >
          Link:{' '}
          <span className={connState === 'open' ? 'text-emerald-600' : 'text-red-600'}>
            {connState}
          </span>
          {linkHealth && ` · ${linkHealth.rssiDbm} dBm · ${linkHealth.linkState}`}
        </div>
      )}
      <Viewer full timeline={false} animation={false} baseLayerPicker={false}>
        {visibility.aoi && <AoiLayer aoi={mission.areaOfInterest} />}
        {visibility.trajectory && <TrajectoryLayer track={track} isLive={isLive} />}
        {coverageProduct && (
          <CoverageRasterLayer
            url={coverageProduct.url}
            format="png-tiles"
            visible={visibility.coverage}
          />
        )}
      </Viewer>
      <div className="absolute bottom-4 left-4 z-10">
        <LayerToggle
          visibility={visibility}
          onChange={setVisibility}
          disabled={{ coverage: !coverageProduct }}
        />
      </div>
    </div>
  );
}
