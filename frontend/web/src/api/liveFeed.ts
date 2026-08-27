import type { LiveFeedMessage } from '@/types/liveFeed';

const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? 'ws://localhost:8080/v1';

export function connectLiveFeed(
  missionId: string,
  onMessage: (msg: LiveFeedMessage) => void,
  onLinkStateChange?: (state: 'connecting' | 'open' | 'closed') => void,
): () => void {
  let socket: WebSocket | null = null;
  let retryDelayMs = 1000;
  let closedByCaller = false;

  function connect() {
    onLinkStateChange?.('connecting');
    socket = new WebSocket(`${WS_BASE}/missions/${missionId}/live`);

    socket.onopen = () => {
      retryDelayMs = 1000;
      onLinkStateChange?.('open');
    };
    socket.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data) as LiveFeedMessage);
      } catch {
        console.warn('live feed: unparseable message', ev.data);
      }
    };
    socket.onclose = () => {
      onLinkStateChange?.('closed');
      if (closedByCaller) return;
      setTimeout(connect, retryDelayMs);
      retryDelayMs = Math.min(retryDelayMs * 2, 15_000);
    };
    socket.onerror = () => socket?.close();
  }

  connect();
  return () => {
    closedByCaller = true;
    socket?.close();
  };
}
