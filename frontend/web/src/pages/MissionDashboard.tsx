import { useQuery } from '@tanstack/react-query';
import { missionApi } from '@/api/missions';
import { MissionTable } from '@/components/MissionTable';
import { MissionCard } from '@/components/MissionCard';

export default function MissionDashboard() {
  const {
    data: missions,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['missions'],
    queryFn: missionApi.list,
    refetchInterval: 15_000, 
  });

  if (isLoading) return <div className="p-6 text-slate-500">Loading missions…</div>;
  if (isError) {
    return (
      <div className="p-6 text-red-600">
        Failed to load missions: {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-4 text-xl font-semibold text-slate-800">Missions</h1>
      <div className="hidden md:block">
        <MissionTable missions={missions ?? []} />
      </div>
      <div className="grid grid-cols-1 gap-3 md:hidden">
        {(missions ?? []).map((m) => (
          <MissionCard key={m.id} mission={m} />
        ))}
      </div>
    </div>
  );
}
