import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { StatusPill } from "../common/StatusPill";
import type { RunSnapshot } from "../../api/client";
import "../RunPanel/RunPanel.css";
import "./CoreCreditRunPanel.css";

interface NodeInfo {
  key: string;
  label: string;
}

interface NodeGroup {
  title: string;
  description: string;
  nodes: NodeInfo[];
}

// Mirrors the orchestrator's own four tiers (core_credit/agent/orchestrator/graph.py) --
// see "Agentic Workflow.pdf" for the diagram this was built from.
const NODE_GROUPS: NodeGroup[] = [
  {
    title: "Prepare & validate data",
    description: "Two agents trim the raw export and screen it for duplicates/test rows.",
    nodes: [
      { key: "clean_columns", label: "Column Cleaner (agent)" },
      { key: "check_rows", label: "Row Checker (agent)" },
    ],
  },
  {
    title: "Dashboard visuals",
    description: "Independent of the data pipeline -- matches each subsection to its PowerBI screenshot.",
    nodes: [{ key: "resolve_dashboard_visuals", label: "Resolve dashboard visuals" }],
  },
  {
    title: "Build component metrics (9 sections, in parallel)",
    description: "Each section computes its own metrics, benchmarks, and qualitative themes.",
    nodes: [
      { key: "build_client_profile", label: "Client Profile & Methodology" },
      { key: "build_financial_access", label: "Financial Access" },
      { key: "build_poverty_likelihood", label: "Poverty Likelihood (PPI)" },
      { key: "build_business_household_impact", label: "Business & Household Impact" },
      { key: "build_child_wellbeing", label: "Child Wellbeing" },
      { key: "build_client_protection", label: "Client Protection" },
      { key: "build_agency", label: "Agency" },
      { key: "build_resilience", label: "Resilience" },
      { key: "build_client_satisfaction", label: "Client Satisfaction" },
    ],
  },
  {
    title: "Build derived outputs",
    description: "Cross-cutting sections that read across all 9 themes above.",
    nodes: [
      { key: "build_executive_summary", label: "Executive Summary" },
      { key: "build_gender_scorecard", label: "Gender Scorecard" },
      { key: "build_client_voices", label: "Client Voices" },
    ],
  },
  {
    title: "Render and review",
    description: "Assembles the .docx and runs a Claude QA read of the finished document.",
    nodes: [
      { key: "assemble_report", label: "Assemble report" },
      { key: "render_docx", label: "Render .docx" },
      { key: "qa_review", label: "QA read (Claude)" },
    ],
  },
];

export function CoreCreditRunPanel({
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
  const nodesDone = snapshot?.core_credit_nodes ?? {};
  const result = snapshot?.core_credit_result ?? {};
  const missingCount = result.visuals_missing?.length ?? 0;
  const issueCount = result.completeness_issues?.length ?? 0;

  return (
    <Card
      title="3. Generate the report"
      subtitle="Runs the full pipeline end to end -- typically 40-90+ minutes for the global portfolio."
      right={
        <Button variant="primary" disabled={!canStart || starting} onClick={onStart}>
          {starting ? "Starting…" : "Generate Core Credit report"}
        </Button>
      }
    >
      {startError && <p className="field-error">{startError}</p>}

      <div className="node-group-list">
        {NODE_GROUPS.map((group) => (
          <div key={group.title} className="node-group">
            <div className="node-group__header">
              <strong>{group.title}</strong>
              <p>{group.description}</p>
            </div>
            <div className="stage-list">
              {group.nodes.map((node) => (
                <div key={node.key} className="stage-row stage-row--compact">
                  <div className="stage-row__main">
                    <span>{node.label}</span>
                    <StatusPill status={nodesDone[node.key] === "done" ? "succeeded" : "pending"} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {(missingCount > 0 || issueCount > 0) && (
        <p className="stage-row__note">
          {missingCount > 0 && `${missingCount} dashboard visual(s) missing (rendered as placeholder text). `}
          {issueCount > 0 && `${issueCount} completeness issue(s) to review.`}
        </p>
      )}

      {snapshot?.error && <p className="field-error">{snapshot.error}</p>}
    </Card>
  );
}
