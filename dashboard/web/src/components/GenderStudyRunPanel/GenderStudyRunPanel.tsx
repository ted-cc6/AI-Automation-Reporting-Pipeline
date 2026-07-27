import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import type { RunSnapshot } from "../../api/client";
import "../RunPanel/RunPanel.css";

const STAGES: { key: "stage1" | "stage2" | "stage3" | "stage4" | "stage5" | "stage6"; label: string; description: string }[] = [
  { key: "stage1", label: "1. Ingest & clean", description: "Parse the survey CSV, drop PII, normalize sex/disability fields" },
  { key: "stage2", label: "2. Quantitative engine", description: "Gender/disability/NPS comparisons with significance testing" },
  { key: "stage3", label: "3. Codebook check", description: "Seed this project's already-reviewed theme codebooks for this run" },
  { key: "stage4", label: "4. Qualitative coding", description: "Code every response against the approved codebooks" },
  { key: "stage5", label: "5. Triangulation", description: "Merge quant + qual evidence into one pack per report section" },
  { key: "stage6", label: "6. Draft writing + assembly", description: "Write section prose, then assemble the .docx and .xlsx" },
];

const PART_LABELS: Record<string, string> = {
  nps_detractor_reasons: "Detractor reasons (score 0-6)",
  nps_passive_reasons: "Passive reasons (score 7-8)",
  nps_promoter_reasons: "Promoter reasons (score 9-10)",
};

export function GenderStudyRunPanel({
  canStart,
  starting,
  onStart,
  snapshot,
  startError,
}: {
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  snapshot: RunSnapshot | null;
  startError: string | null;
}) {
  return (
    <Card
      title="3. Generate the report"
      subtitle="Runs all six stages end to end."
      right={
        <Button variant="primary" disabled={!canStart || starting} onClick={onStart}>
          {starting ? "Starting…" : "Generate Gender Study report"}
        </Button>
      }
    >
      {startError && <p className="field-error">{startError}</p>}

      <div className="stage-list">
        {STAGES.map((stage) => {
          const info = snapshot ? snapshot[stage.key] : null;
          const status = info?.status ?? "pending";
          return (
            <div key={stage.key} className="stage-row">
              <div className="stage-row__main">
                <div>
                  <strong>{stage.label}</strong>
                  <p>{stage.description}</p>
                </div>
                <StatusPill status={status} />
              </div>

              {stage.key === "stage4" && snapshot?.stage4?.parts && Object.keys(snapshot.stage4.parts).length > 0 && (
                <ul className="part-list">
                  {Object.entries(snapshot.stage4.parts).map(([key, part]) => (
                    <li key={key} className="part-list__row">
                      <span>{PART_LABELS[key] ?? key}</span>
                      <StatusPill status={part.status} />
                      {part.error && <span className="part-list__error">{part.error}</span>}
                    </li>
                  ))}
                </ul>
              )}

              {(info as { error?: string } | null)?.error && (
                <p className="stage-row__errors">{(info as { error?: string }).error}</p>
              )}
            </div>
          );
        })}
      </div>

      {snapshot?.error && <p className="field-error">{snapshot.error}</p>}
    </Card>
  );
}
