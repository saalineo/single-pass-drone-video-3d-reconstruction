import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { missionApi } from '@/api/missions';
import { useMissionStatus } from '@/hooks/useMissionStatus';
import { Viewer3D } from '@/components/Viewer3D';
import { MapViewer } from '@/components/MapViewer';
import { StatusBadge } from '@/components/StatusBadge';
import { ProgressLadder } from '@/components/ProgressLadder';
import { QualityBadge } from '@/components/QualityBadge';
import { CoverageGapBadge } from '@/components/CoverageGapBadge';
import { ProductToggle } from '@/components/ProductToggle';
import { AccuracyWarningBanner } from '@/components/AccuracyWarningBanner';
import type { ProductQuality } from '@/types/product';

const PRODUCTS_ERROR_TOAST_ID = 'products-error';

export default function MissionDetails() {
  const { missionId } = useParams<{ missionId: string }>();
  const [quality, setQuality] = useState<ProductQuality>('survey');

  const { data: mission, isLoading: missionLoading } = useQuery({
    queryKey: ['mission', missionId],
    queryFn: () => missionApi.get(missionId!),
    enabled: !!missionId,
  });
  const {
    data: products,
    refetch: refetchProducts,
    isError: productsError,
  } = useQuery({
    queryKey: ['products', missionId],
    queryFn: () => missionApi.getProducts(missionId!),
    enabled: !!missionId,
    retry: 2,
  });
  const { status, connState } = useMissionStatus(missionId!, mission);

  useEffect(() => {
    if (productsError) {
      toast.custom(
        (t) => (
          <div
            className="flex items-center gap-3 rounded-md bg-slate-800 px-4 py-3 text-sm
            text-white shadow-lg"
            style={{ opacity: t.visible ? 1 : 0 }}
          >
            Failed to load mission products.
            <button
              className="rounded bg-white/20 px-2 py-1 text-xs font-medium hover:bg-white/30"
              onClick={() => {
                refetchProducts();
                toast.dismiss(PRODUCTS_ERROR_TOAST_ID);
              }}
            >
              Retry
            </button>
          </div>
        ),
        { duration: Infinity, id: PRODUCTS_ERROR_TOAST_ID },
      );
    } else {
      toast.dismiss(PRODUCTS_ERROR_TOAST_ID);
    }
  }, [productsError, refetchProducts]);

  if (missionLoading || !mission) {
    return <div className="p-6 text-slate-500">Loading mission…</div>;
  }

  const visibleProducts = (products ?? []).filter((p) => p.quality === quality);
  const meshOrSplatVariants = (products ?? []).filter(
    (p) => p.kind === 'mesh_glb' || p.kind === 'gaussian_splat',
  );
  const coverageProduct = products?.find((p) => p.kind === 'confidence_raster');

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-slate-800">{mission.name}</h1>
        <StatusBadge status={status?.overallStatus ?? mission.status} />
        {coverageProduct?.coveragePct != null && (
          <CoverageGapBadge coveragePct={coverageProduct.coveragePct} />
        )}
        <ProductToggle variants={meshOrSplatVariants} selected={quality} onChange={setQuality} />
      </header>

      {status?.accuracyWarning && <AccuracyWarningBanner message={status.accuracyWarning} />}

      {mission.status !== 'complete' && (
        <section className="rounded-lg border border-slate-200 p-4">
          <ProgressLadder stages={status?.stages ?? mission.stages} />
        </section>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="text-sm font-medium text-slate-600">3D Product</h2>
            {visibleProducts[0] && <QualityBadge quality={visibleProducts[0].quality} />}
          </div>
          <Viewer3D products={visibleProducts} />
        </section>
        <section>
          <h2 className="mb-2 text-sm font-medium text-slate-600">
            Geographic Context {connState === 'open' && '· live'}
          </h2>
          <MapViewer mission={mission} products={products ?? []} />
        </section>
      </div>
    </div>
  );
}
