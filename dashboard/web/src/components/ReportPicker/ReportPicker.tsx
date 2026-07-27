import { Button } from "../common/Button";
import type { ReportType } from "../../api/client";
import "./ReportPicker.css";

const OPTIONS: { type: ReportType; title: string; description: string }[] = [
  {
    type: "cupboard_week",
    title: "Insurance Cupboard Week Report",
    description:
      "The quarterly VFI Insurance Impact Report: client understanding, claims experience, financial resilience, and child wellbeing, segmented by country.",
  },
  {
    type: "gender_study",
    title: "Insurance Gender Study Report",
    description:
      "The GEDSI (Gender Equality, Disability, and Social Inclusion) analysis report: gender and disability comparisons across the insurance client survey.",
  },
];

export function ReportPicker({ onSelect }: { onSelect: (type: ReportType) => void }) {
  return (
    <div className="report-picker">
      <h2>What do you want to generate today?</h2>
      <p className="report-picker__intro">Pick a report to continue to its setup flow.</p>
      <div className="report-picker__grid">
        {OPTIONS.map((opt) => (
          <div key={opt.type} className="report-picker__card">
            <h3>{opt.title}</h3>
            <p>{opt.description}</p>
            <Button variant="primary" onClick={() => onSelect(opt.type)}>
              Continue
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
