import { Link } from 'react-router-dom';
import type { Mission } from '@/types/mission';
import { StatusBadge } from './StatusBadge';

export function MissionTable({ missions }: { missions: Mission[] }) {
  return (
    <table className="min-w-full divide-y divide-slate-200 text-sm">
      <thead>
        <tr className="text-left text-slate-500">
          <th className="py-2 pr-4">Mission</th>
          <th className="py-2 pr-4">Status</th>
          <th className="py-2 pr-4">Created</th>
          <th className="py-2 pr-4">Area (km²)</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {missions.map((m) => (
          <tr key={m.id} className="hover:bg-slate-50">
            <td className="py-2 pr-4">
              <Link to={`/missions/${m.id}`} className="font-medium text-sky-700">
                {m.name}
              </Link>
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={m.status} />
            </td>
            <td className="py-2 pr-4 text-slate-500">
              {new Date(m.createdAt).toLocaleString()}
            </td>
            <td className="py-2 pr-4 text-slate-500">{m.areaSqKm.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
