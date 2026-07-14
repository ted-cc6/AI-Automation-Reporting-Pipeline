import logo from "../../assets/logo.svg";
import "./Header.css";

export function Header() {
  return (
    <header className="app-header">
      <img src={logo} alt="VisionFund International" className="app-header__logo" />
      <div className="app-header__title">
        <h1>Insurance Impact Report Dashboard</h1>
        <p>Upload survey data, choose a language model, and generate the quarterly report.</p>
      </div>
    </header>
  );
}
