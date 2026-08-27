import { useEffect, useRef, useState } from 'react';
import { connectLiveFeed } from '@/api/liveFeed';
import type { CoverageAlert, LinkHealth, PoseTrailFeature } from '@/types/liveFeed';
import type { MissionOverallStatus } from '@/types/mission';

export function useLiveTrajectory(missionId: string, status: MissionOverallStatus) {
  const [track, setTrack] = useState<PoseTrailFeature[]>([]);
  const [alerts, setAlerts] = useState<CoverageAlert[]>([]);
  const [linkHealth, setLinkHealth] = useState<LinkHealth | null>(null);
  const [connState, setConnState] = useState<'connecting' | 'open' | 'closed'>('closed');
  const disconnectRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (status !== 'in_flight') return; // completed missions read O-5 statically instead
    disconnectRef.current = connectLiveFeed(
      missionId,
      (msg) => {
        if (msg.type === 'pose') setTrack((t) => [...t, msg.payload]);
        if (msg.type === 'alert') setAlerts((a) => [msg.payload, ...a].slice(0, 20));
        if (msg.type === 'link_health') setLinkHealth(msg.payload);
      },
      setConnState,
    );
    return () => disconnectRef.current?.();
  }, [missionId, status]);

  return { track, alerts, linkHealth, connState };
}
