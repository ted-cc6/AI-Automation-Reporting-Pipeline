import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import { downloadUrl, downloadXlsxUrl } from "../../api/client";
import type { RunSnapshot } from "../../api/client";
import "../ResultsPanel/ResultsPanel.css";
import "./GenderStudyResultsPanel.css";

export function GenderStudyResultsPanel({ snapshot }: { snapshot: RunSnapshot }) {
  return (
    <Card
      title="Report ready"
      subtitle={`Run ${snapshot.run_id}`}
      right={<StatusPill status={snapshot.status} />}
    >
      <div className="results-summary">
        <p className="results-summary__ok">Every stage completed cleanly.</p>
      </div>

      <div className="results-summary__downloads">
        {snapshot.docx_ready && (
          <a href={downloadUrl(snapshot.run_id)} download>
            <Button variant="primary">Download report (.docx)</Button>
          </a>
        )}
        {snapshot.xlsx_ready && (
          <a href={downloadXlsxUrl(snapshot.run_id)} download>
            <Button variant="secondary">Download supporting workbook (.xlsx)</Button>
          </a>
        )}
      </div>

      {!snapshot.docx_ready && <p>The report file isn't ready yet.</p>}
    </Card>
  );
}
