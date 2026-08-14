import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import type { RunSnapshot } from "../../api/client";
import "./RunPanel.css";

const STAGES: { key: "stage1" | "stage2" | "stage3" | "stage4"; label: string; description: string }[] = [
  { key: "stage1", label: "1. Data loading", description: "Clean and validate the uploaded survey CSV" },
  { key: "stage2", label: "2. Analysis", description: "Compute segments, statistics, and the Kling Index" },
  { key: "stage3", label: "3. Qualitative tagging", description: "Batched LLM calls over open-ended responses" },
  { key: "stage4", label: "4. Report generation", description: "Seven LLM calls, one per report part, then assembly" },
];

const PART_LABELS: Record<string, string> = {
  part_1: "Part 1 — Client Understanding",
  part_2: "Part 2 — Claims Experience",
  part_3: "Part 3 — Financial Resilience",
  part_4: "Part 4 — Child Wellbeing",
  part_5: "Part 5 — CWB Drivers",
  part_6: "Part 6 — Claimant Scorecard",
  part_7: "Part 7 — Gender Scorecard",
};

export function RunPanel({
  canStart,
  starting,
  onStart,
  snapshot,
  startError,
  dryRun,
}: {
  canStart: boolean;
  starting: boolean;
  onStart: () => void;
  snapshot: RunSnapshot | null;
  startError: string | null;
  dryRun?: boolean;
}) {
  return (
    <Card
      title="5. Generate the report"
      subtitle={
        dryRun
          ? "Runs data cleaning and analysis only (stages 1-2) -- no LLM calls, no .docx."
          : "Runs all four stages end to end for the selected quarter."
      }
      right={
        <Button variant="primary" disabled={!canStart || starting} onClick={onStart}>
          {starting ? "Starting…" : dryRun ? "Run analysis only" : "Generate quarterly report"}
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

              {stage.key === "stage2" && !!info?.section_errors && Object.keys(info.section_errors as object).length > 0 && (
                <ul className="stage-row__errors">
                  {Object.entries(info.section_errors as Record<string, { error: string }>).map(([k, e]) => (
                    <li key={k}>
                      {k}: {e.error}
                    </li>
                  ))}
                </ul>
              )}

              {stage.key === "stage3" && info?.status === "failed" && (
                <p className="stage-row__note">
                  {String((info as { error?: string }).error ?? "")} — the report will still generate without
                  qualitative themes and verbatims.
                </p>
              )}

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
              {stage.key === "stage4" && snapshot?.stage4?.status === "partial_failure" && (
                <p className="stage-row__note">
                  One or more parts need manual write-up — the report still includes their tables and visuals,
                  with a placeholder in place of the narrative.
                </p>
              )}
            </div>
          );
        })}
      </div>

      {snapshot?.error && <p className="field-error">{snapshot.error}</p>}
    </Card>
  );
}
