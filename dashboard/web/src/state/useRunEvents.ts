import { useEffect, useRef, useState } from "react";
import type { RunSnapshot } from "../api/client";

interface RunEventPayload {
  seq: number;
  line: string;
  snapshot: RunSnapshot;
}

export function useRunEvents(runId: string | null) {
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    setSnapshot(null);
    setLogLines([]);
    if (!runId) return;

    const es = new EventSource(`/api/runs/${runId}/events`);
    sourceRef.current = es;

    es.onmessage = (ev) => {
      const data: RunEventPayload = JSON.parse(ev.data);
      setSnapshot(data.snapshot);
      setLogLines((prev) => [...prev, data.line]);
    };
    // EventSource auto-reconnects on drop and resends Last-Event-ID itself;
    // no manual reconnect logic needed here.

    return () => {
      es.close();
      sourceRef.current = null;
    };
  }, [runId]);

  return { snapshot, logLines };
}
