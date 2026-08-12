import { useState } from "react";
import { Header } from "./components/common/Header";
import { LandingPage } from "./components/LandingPage/LandingPage";
import { CupboardWeekApp } from "./CupboardWeekApp";
import { GenderStudyApp } from "./GenderStudyApp";
import { CoreCreditApp } from "./CoreCreditApp";
import type { Product, ReportType } from "./api/client";
import "./App.css";

export default function App() {
  // null = landing page (no space chosen yet). Insurance itself still offers
  // a second-level choice (cupboard_week vs gender_study) via reportType,
  // exactly as before -- Core Credit has only the one report type, so it
  // doesn't need an equivalent selector once inside.
  const [product, setProduct] = useState<Product | null>(null);
  const [reportType, setReportType] = useState<ReportType>("cupboard_week");

  return (
    <div className="app-shell">
      <Header product={product} onChangeProduct={() => setProduct(null)} />
      <main className="app-main">
        {product === null && <LandingPage onSelect={setProduct} />}

        {product === "insurance" &&
          (reportType === "gender_study" ? (
            <GenderStudyApp reportType={reportType} onReportTypeChange={setReportType} />
          ) : (
            <CupboardWeekApp reportType={reportType} onReportTypeChange={setReportType} />
          ))}

        {product === "core_credit" && <CoreCreditApp />}
      </main>
    </div>
  );
}
