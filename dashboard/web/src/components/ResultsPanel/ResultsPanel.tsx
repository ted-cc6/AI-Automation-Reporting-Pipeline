import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import { downloadUrl } from "../../api/client";
import type { RunSnapshot } from "../../api/client";
import "./ResultsPanel.css";

export function ResultsPanel({ snapshot }: { snapshot: RunSnapshot }) {
  const sectionErrorCount = Object.keys((snapshot.stage2.section_errors as object) ?? {}).length;
  const failedParts = Object.entries(snapshot.stage4.parts ?? {}).filter(([, p]) => p.status === "failed");

  return (
    <Card
      title="Report ready"
      subtitle={`Run ${snapshot.run_id}`}
      right={<StatusPill status={snapshot.status} />}
    >
      <div className="results-summary">
        {sectionErrorCount > 0 && (
          <p className="results-summary__note">
            {sectionErrorCount} analysis section{sectionErrorCount > 1 ? "s" : ""} failed and were left out of the
            report.
          </p>
        )}
        {snapshot.stage3.status === "failed" && (
          <p className="results-summary__note">Qualitative themes and verbatims were not available for this run.</p>
        )}
        {failedParts.length > 0 && (
          <p className="results-summary__note">
            {failedParts.length} report part{failedParts.length > 1 ? "s" : ""} need manual write-up (marked in the
            document).
          </p>
        )}
        {sectionErrorCount === 0 && snapshot.stage3.status !== "failed" && failedParts.length === 0 && (
          <p className="results-summary__ok">Every stage completed cleanly.</p>
        )}
      </div>

      {snapshot.docx_ready ? (
        <a href={downloadUrl(snapshot.run_id)} download>
          <Button variant="primary">Download report (.docx)</Button>
        </a>
      ) : (
        <p>The report file isn't ready yet.</p>
      )}
    </Card>
  );
}
