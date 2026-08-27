import type { MissionOverallStatus } from '@/types/mission';

const LABEL: Record<MissionOverallStatus, string> = {
  queued: 'Queued',
  in_flight: 'In Flight',
  processing: 'Processing',
  complete: 'Complete',
  failed: 'Failed',
};
const CLASS: Record<MissionOverallStatus, string> = {
  queued: 'bg-status-queued',
  in_flight: 'bg-status-inflight',
  processing: 'bg-status-processing',
  complete: 'bg-status-complete',
  failed: 'bg-status-failed',
};

export function StatusBadge({ status }: { status: MissionOverallStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs
      font-medium text-white ${CLASS[status]}`}
    >
      {LABEL[status]}
    </span>
  );
}
