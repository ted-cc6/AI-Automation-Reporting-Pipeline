import type { ReactNode } from "react";
import type { Product } from "../../api/client";
import "./LandingPage.css";

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3.5l6.5 2.6v5.4c0 4.2-2.8 7.6-6.5 8.6-3.7-1-6.5-4.4-6.5-8.6V6.1L12 3.5z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  );
}

function GrowthIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="20" x2="5" y2="12" />
      <line x1="12" y1="20" x2="12" y2="5" />
      <line x1="19" y1="20" x2="19" y2="15.5" />
      <path d="M4 9.5l4.5-4 3.5 3 5.5-5.5" strokeWidth="1.3" opacity="0.55" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="landing-tile__arrow-icon">
      <line x1="4" y1="12" x2="19" y2="12" />
      <polyline points="13 6 19 12 13 18" />
    </svg>
  );
}

const TILES: { product: Product; icon: ReactNode; title: string; description: string; meta: string }[] = [
  {
    product: "insurance",
    icon: <ShieldIcon />,
    title: "Insurance Impact Reports",
    description:
      "Cupboard Week quarterly impact reports and the Gender Study report, generated from a client-survey CSV export.",
    meta: "2 report types · bring your own Gemini, Anthropic, or OpenAI key",
  },
  {
    product: "core_credit",
    icon: <GrowthIcon />,
    title: "Core Credit Impact Report",
    description:
      "The global, multi-country Core Credit portfolio report -- 9 theme sections, benchmarked against the MFI Index.",
    meta: "1 report type · bring your own Anthropic key",
  },
];

export function LandingPage({ onSelect }: { onSelect: (product: Product) => void }) {
  return (
    <div className="landing">
      <div className="landing-grid">
        {TILES.map((tile) => (
          <button key={tile.product} className="landing-tile" onClick={() => onSelect(tile.product)}>
            <span className="landing-tile__icon">{tile.icon}</span>
            <h3>{tile.title}</h3>
            <p>{tile.description}</p>
            <span className="landing-tile__footer">
              <span className="landing-tile__meta">{tile.meta}</span>
              <span className="landing-tile__cta">
                Enter
                <ArrowIcon />
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
