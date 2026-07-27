import { useState } from "react";
import { Header } from "./components/common/Header";
import { ReportPicker } from "./components/ReportPicker/ReportPicker";
import { CupboardWeekApp } from "./CupboardWeekApp";
import { GenderStudyApp } from "./GenderStudyApp";
import type { ReportType } from "./api/client";
import "./App.css";

export default function App() {
  const [reportType, setReportType] = useState<ReportType | null>(null);

  if (reportType === "cupboard_week") {
    return <CupboardWeekApp onBack={() => setReportType(null)} />;
  }
  if (reportType === "gender_study") {
    return <GenderStudyApp onBack={() => setReportType(null)} />;
  }

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <ReportPicker onSelect={setReportType} />
      </main>
    </div>
  );
}
