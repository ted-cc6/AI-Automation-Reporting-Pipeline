import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import { downloadUrl } from "../../api/client";
import type { RunSnapshot } from "../../api/client";
import "../ResultsPanel/ResultsPanel.css";

export function CoreCreditResultsPanel({ snapshot }: { snapshot: RunSnapshot }) {
  const missing = snapshot.core_credit_result?.visuals_missing ?? [];
  const issues = snapshot.core_credit_result?.completeness_issues ?? [];

  return (
    <Card
      title="Report ready"
      subtitle={`Run ${snapshot.run_id}`}
      right={<StatusPill status={snapshot.status} />}
    >
      <div className="results-summary">
        {missing.length === 0 && issues.length === 0 ? (
          <p className="results-summary__ok">Every tier completed cleanly, and every dashboard visual was found.</p>
        ) : (
          <>
            {missing.length > 0 && (
              <p className="results-summary__note">
                {missing.length} dashboard visual{missing.length > 1 ? "s" : ""} missing -- rendered as template
                placeholder text: {missing.join(", ")}
              </p>
            )}
            {issues.length > 0 && (
              <>
                <p className="results-summary__note">
                  {issues.length} completeness issue{issues.length > 1 ? "s" : ""} to review before publishing:
                </p>
                <ul className="results-summary__issues">
                  {issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </>
            )}
          </>
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
