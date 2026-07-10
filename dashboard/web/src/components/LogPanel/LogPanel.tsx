import { useEffect, useRef } from "react";
import { Card } from "../common/Card";
import "./LogPanel.css";

export function LogPanel({ lines }: { lines: string[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [lines.length]);

  return (
    <Card title="Progress log" subtitle="Live output from the pipeline.">
      <div className="log-panel">
        {lines.length === 0 ? (
          <p className="log-panel__empty">Nothing yet — start a run to see progress here.</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="log-panel__line">
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </Card>
  );
}
