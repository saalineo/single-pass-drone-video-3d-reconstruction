import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { connectLiveFeed } from '@/api/liveFeed';
import type { MissionStatusPayload } from '@/types/liveFeed';
import type { Mission } from '@/types/mission';

export function useMissionStatus(missionId: string, initial: Mission | undefined) {
  const [status, setStatus] = useState<MissionStatusPayload | null>(null);
  const [connState, setConnState] = useState<'connecting' | 'open' | 'closed'>('closed');
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!initial || initial.status === 'complete' || initial.status === 'failed') {
      return; // terminal missions don't need a live socket; the fetched Mission is final
    }
    return connectLiveFeed(
      missionId,
      (msg) => {
        if (msg.type !== 'status') return;
        setStatus(msg.payload);
        // Keep the React Query cache for ['mission', missionId] in sync so any
        // other component reading the mission (e.g. the dashboard, if visited
        // via back-navigation) sees the fresh status without a refetch.
        queryClient.setQueryData(['mission', missionId], (old: Mission | undefined) =>
          old ? { ...old, status: msg.payload.overallStatus, stages: msg.payload.stages } : old,
        );
      },
      setConnState,
    );
  }, [missionId, initial, queryClient]);

  useEffect(() => {
    // Mobile/tablet browsers suspend timers/sockets when backgrounded; force
    // a refetch on return-to-foreground as a correctness backstop, since
    // socket resume timing after backgrounding isn't guaranteed.
    function onVisibilityChange() {
      if (document.visibilityState === 'visible') {
        queryClient.invalidateQueries({ queryKey: ['mission', missionId] });
      }
    }
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [missionId, queryClient]);

  return { status, connState };
}
