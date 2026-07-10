import "./StatusPill.css";

type Kind = "pending" | "running" | "success" | "warning" | "error";

const KIND_BY_STATUS: Record<string, Kind> = {
  pending: "pending",
  queued: "pending",
  running: "running",
  succeeded: "success",
  partial_failure: "warning",
  failed: "error",
  skipped_dry_run: "pending",
};

const LABEL_BY_STATUS: Record<string, string> = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  partial_failure: "Partial",
  failed: "Failed",
  skipped_dry_run: "Skipped",
};

export function StatusPill({ status }: { status: string }) {
  const kind = KIND_BY_STATUS[status] ?? "pending";
  const label = LABEL_BY_STATUS[status] ?? status;
  return (
    <span className={`status-pill status-pill--${kind}`}>
      <span className="status-pill__dot" />
      {label}
    </span>
  );
}
