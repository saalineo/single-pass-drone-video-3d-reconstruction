import type { StageState } from '@/types/mission';

const STAGE_LABEL: Record<StageState['stage'], string> = {
  ingest: 'Ingest & Curation',
  pose_estimation: 'Pose Estimation',
  dynamic_masking: 'Dynamic Masking',
  depth_fusion: 'Depth Fusion',
  meshing: 'Meshing',
  georeferencing: 'Georeferencing',
  publishing: 'Publishing',
};

const STATE_DOT: Record<StageState['state'], string> = {
  pending: 'bg-slate-300',
  running: 'bg-sky-500 animate-pulse',
  complete: 'bg-emerald-500',
  failed: 'bg-red-500',
};

export function ProgressLadder({ stages }: { stages: StageState[] }) {
  return (
    <ol className="space-y-2">
      {stages.map((s) => (
        <li key={s.stage} className="flex items-center gap-3 text-sm">
          <span className={`h-2.5 w-2.5 rounded-full ${STATE_DOT[s.state]}`} />
          <span className="w-40 text-slate-700">{STAGE_LABEL[s.stage]}</span>
          <div className="h-1.5 flex-1 rounded-full bg-slate-100">
            <div
              className="h-1.5 rounded-full bg-sky-500 transition-all"
              style={{ width: `${s.progressPct}%` }}
            />
          </div>
          <span className="w-16 text-right text-slate-400">
            {s.state === 'running' && s.etaSeconds != null
              ? `${Math.ceil(s.etaSeconds / 60)}m left`
              : `${s.progressPct}%`}
          </span>
        </li>
      ))}
    </ol>
  );
}
