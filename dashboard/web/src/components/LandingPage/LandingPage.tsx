import type { Product } from "../../api/client";
import "./LandingPage.css";

const TILES: { product: Product; title: string; description: string; meta: string }[] = [
  {
    product: "insurance",
    title: "Insurance Impact Reports",
    description:
      "Cupboard Week quarterly impact reports and the Gender Study report, generated from a client-survey CSV export.",
    meta: "2 report types · bring your own Gemini, Anthropic, or OpenAI key",
  },
  {
    product: "core_credit",
    title: "Core Credit Impact Report",
    description:
      "The global, multi-country Core Credit portfolio report -- 9 theme sections, benchmarked against the MFI Index.",
    meta: "1 report type · bring your own Anthropic key",
  },
];

export function LandingPage({ onSelect }: { onSelect: (product: Product) => void }) {
  return (
    <div className="landing">
      <h2 className="landing__heading">What would you like to work on today?</h2>
      <p className="landing__subheading">Pick a report family to get started. You can switch back at any time.</p>
      <div className="landing-grid">
        {TILES.map((tile) => (
          <button key={tile.product} className="landing-tile" onClick={() => onSelect(tile.product)}>
            <h3>{tile.title}</h3>
            <p>{tile.description}</p>
            <span className="landing-tile__meta">{tile.meta}</span>
            <span className="landing-tile__cta">Enter →</span>
          </button>
        ))}
      </div>
    </div>
  );
}
