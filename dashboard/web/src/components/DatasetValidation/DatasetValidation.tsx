import { useState } from "react";
import { Button } from "../common/Button";
import { validateDataset, applyDecisions } from "../../api/client";
import type { ApplyDecisionsResponse, Provider, Recommendation } from "../../api/client";
import "./DatasetValidation.css";

type Phase = "idle" | "checking" | "clean" | "needs-review" | "applying" | "applied-pass" | "applied-fail" | "error";

const TYPE_LABEL: Record<Recommendation["type"], string> = {
  rename: "Renamed",
  new_question: "New question",
  dropped: "Dropped",
};
const TYPE_BADGE_CLASS: Record<Recommendation["type"], string> = {
  rename: "badge--pending",
  new_question: "badge--success",
  dropped: "badge--error",
};

function confidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.8) return "badge--success";
  if (confidence >= 0.5) return "badge--warning";
  return "badge--error";
}

export function DatasetValidation(props: {
  endpointBase: string;
  uploadId: string;
  provider: Provider;
  apiKey: string;
  disabled: boolean;
  onResolved: (ready: boolean) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [decisions, setDecisions] = useState<Record<string, boolean>>({});
  const [applyResult, setApplyResult] = useState<ApplyDecisionsResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [residualCounts, setResidualCounts] = useState({ old: 0, new: 0 });

  const busy = phase === "checking" || phase === "applying";
  const showRecommendations = phase === "needs-review" || phase === "applied-fail" || phase === "applying";
  const allDecided = recommendations.length > 0 && recommendations.every((r) => decisions[r.id] !== undefined);

  async function handleValidate() {
    setPhase("checking");
    setErrorMessage(null);
    props.onResolved(false);
    try {
      const result = await validateDataset(props.endpointBase, props.uploadId, props.provider, props.apiKey);
      if (result.clean) {
        setPhase("clean");
        setRecommendations([]);
        props.onResolved(true);
      } else {
        const sorted = [...result.recommendations].sort((a, b) => b.confidence - a.confidence);
        setRecommendations(sorted);
        setDecisions({});
        setResidualCounts({ old: result.residual_old_count, new: result.residual_new_count });
        setPhase("needs-review");
      }
    } catch (err) {
      setPhase("error");
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  }

  function handleDecide(id: string, approved: boolean) {
    setDecisions((prev) => ({ ...prev, [id]: approved }));
  }

  async function handleApply() {
    setPhase("applying");
    try {
      const result = await applyDecisions(
        props.endpointBase,
        props.uploadId,
        Object.entries(decisions).map(([id, approved]) => ({ id, approved })),
      );
      setApplyResult(result);
      if (result.validator_passed) {
        setPhase("applied-pass");
        props.onResolved(true);
      } else {
        setPhase("applied-fail");
        props.onResolved(false);
      }
    } catch (err) {
      setPhase("error");
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="dataset-validation">
      <div className="dataset-validation__actions">
        <Button variant="secondary" disabled={props.disabled || busy} onClick={handleValidate}>
          {phase === "checking"
            ? "Checking dataset…"
            : phase === "idle" || phase === "error"
              ? "Validate dataset"
              : "Re-validate dataset"}
        </Button>
      </div>

      {phase === "error" && errorMessage && <p className="field-error">{errorMessage}</p>}

      {phase === "clean" && (
        <p className="field-success">
          Dataset structure matches the current column mapping — nothing needs review. You can continue.
        </p>
      )}

      {showRecommendations && (
        <div className="rec-list">
          <p className="rec-list__summary">
            {residualCounts.old} question(s) and {residualCounts.new} new column(s) in this export couldn't be
            matched automatically. Review each recommendation below — every one needs an explicit decision before
            you can continue.
          </p>
          {recommendations.map((rec) => (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              decision={decisions[rec.id]}
              onDecide={(approved) => handleDecide(rec.id, approved)}
            />
          ))}
          <div className="rec-list__apply-row">
            <Button variant="primary" disabled={!allDecided || phase === "applying"} onClick={handleApply}>
              {phase === "applying" ? "Applying…" : "Apply reconciliation"}
            </Button>
            {!allDecided && <span className="field-error">Decide on every recommendation to continue.</span>}
          </div>
        </div>
      )}

      {phase === "applied-pass" && applyResult && (
        <p className="field-success">
          Reconciled dataset validated successfully — {applyResult.renamed_count} renamed,{" "}
          {applyResult.new_question_count} new question(s), {applyResult.dropped_count} dropped. This run will use
          the adjusted mapping.
        </p>
      )}

      {phase === "applied-fail" && applyResult && (
        <div className="rec-list__errors">
          <p className="field-error">
            The reconciled mapping didn't pass validation. Adjust your decisions above and apply again.
          </p>
          <ul>
            {applyResult.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RecommendationCard({
  rec,
  decision,
  onDecide,
}: {
  rec: Recommendation;
  decision: boolean | undefined;
  onDecide: (approved: boolean) => void;
}) {
  const oldText = rec.type === "new_question" ? "— (new)" : rec.old_header ?? "—";
  const newText = rec.type === "dropped" ? "— (removed)" : rec.new_header ?? "—";

  return (
    <div className="rec-card">
      <div className="rec-card__header">
        <span className={`badge ${TYPE_BADGE_CLASS[rec.type]}`}>{TYPE_LABEL[rec.type]}</span>
        <span className={`badge ${confidenceBadgeClass(rec.confidence)}`}>
          {Math.round(rec.confidence * 100)}% confidence
        </span>
      </div>

      <div className="rec-card__diff">
        <span className="rec-card__diff-old">{oldText}</span>
        <span className="rec-card__diff-arrow">→</span>
        <span className="rec-card__diff-new">{newText}</span>
      </div>

      {rec.type === "new_question" && rec.suggested_question_ref && (
        <p className="rec-card__meta">
          <span className="mono">{rec.suggested_question_ref}</span> · {rec.suggested_response_type}
        </p>
      )}

      {rec.type === "new_question" && rec.suggested_role_type && (
        <p className="rec-card__meta">
          <span className="badge badge--neutral">{rec.suggested_role_type}</span>
          {rec.suggested_role_name && (
            <>
              {" "}
              · <span className="mono">{rec.suggested_role_name}</span>
            </>
          )}
          {rec.suggested_group_name && (
            <>
              {" "}
              · group <span className="mono">{rec.suggested_group_name}</span>
            </>
          )}
          {rec.suggested_option_label && <> · option "{rec.suggested_option_label}"</>}
          {rec.suggested_applies_to && <> · applies to {rec.suggested_applies_to}</>}
        </p>
      )}

      <p className="rec-card__rationale">{rec.rationale}</p>

      {rec.suggested_response_type === "likert5" && rec.suggested_value_map && (
        <table className="rec-card__value-map">
          <thead>
            <tr>
              <th>Raw value</th>
              <th>Int</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rec.suggested_value_map).map(([raw, entry]) => (
              <tr key={raw}>
                <td>{raw}</td>
                <td>{entry.int}</td>
                <td>{entry.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="rec-card__decision">
        <Button
          variant={decision === true ? "primary" : "ghost"}
          aria-pressed={decision === true}
          onClick={() => onDecide(true)}
        >
          Approve
        </Button>
        <Button
          variant={decision === false ? "primary" : "ghost"}
          aria-pressed={decision === false}
          onClick={() => onDecide(false)}
        >
          Reject
        </Button>
      </div>
    </div>
  );
}
