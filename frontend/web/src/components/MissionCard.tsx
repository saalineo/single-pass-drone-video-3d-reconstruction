import { Link } from 'react-router-dom';
import type { Mission } from '@/types/mission';
import { StatusBadge } from './StatusBadge';

export function MissionCard({ mission }: { mission: Mission }) {
  return (
    <Link
      to={`/missions/${mission.id}`}
      className="block rounded-lg border border-slate-200 bg-white p-4 hover:border-sky-300"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sky-700">{mission.name}</span>
        <StatusBadge status={mission.status} />
      </div>
      <div className="mt-2 flex justify-between text-xs text-slate-500">
        <span>{new Date(mission.createdAt).toLocaleString()}</span>
        <span>{mission.areaSqKm.toFixed(2)} km²</span>
      </div>
    </Link>
  );
}
