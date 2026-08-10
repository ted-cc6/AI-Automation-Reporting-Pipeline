import { useState } from "react";
import { Header } from "./components/common/Header";
import { CupboardWeekApp } from "./CupboardWeekApp";
import { GenderStudyApp } from "./GenderStudyApp";
import type { ReportType } from "./api/client";
import "./App.css";

export default function App() {
  const [reportType, setReportType] = useState<ReportType>("cupboard_week");

  return (
    <div className="app-shell">
      <Header />
      <main className="app-main">
        {reportType === "cupboard_week" ? (
          <CupboardWeekApp reportType={reportType} onReportTypeChange={setReportType} />
        ) : (
          <GenderStudyApp reportType={reportType} onReportTypeChange={setReportType} />
        )}
      </main>
    </div>
  );
}
