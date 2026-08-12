import logo from "../../assets/logo.svg";
import type { Product } from "../../api/client";
import "./Header.css";

const TITLE_BY_PRODUCT: Record<Product, string> = {
  insurance: "Insurance Impact Report Dashboard",
  core_credit: "Core Credit Impact Report Dashboard",
};

const SUBTITLE_BY_PRODUCT: Record<Product, string> = {
  insurance: "Upload survey data, choose a language model, and generate the quarterly report.",
  core_credit: "Upload the survey export, provide an Anthropic key, and generate the global portfolio report.",
};

export function Header({
  product,
  onChangeProduct,
}: {
  // null on the landing page, before a space has been chosen.
  product: Product | null;
  onChangeProduct: () => void;
}) {
  return (
    <header className="app-header">
      <img src={logo} alt="VisionFund International" className="app-header__logo" />
      <div className="app-header__title">
        <h1>{product ? TITLE_BY_PRODUCT[product] : "VisionFund Report Dashboard"}</h1>
        <p>
          {product
            ? SUBTITLE_BY_PRODUCT[product]
            : "Pick a report family below to get started."}
        </p>
      </div>
      {product && (
        <button className="app-header__back" onClick={onChangeProduct}>
          ← All reports
        </button>
      )}
    </header>
  );
}
