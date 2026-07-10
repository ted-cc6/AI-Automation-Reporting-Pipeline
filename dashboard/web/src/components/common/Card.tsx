import type { ReactNode } from "react";
import "./Card.css";

export function Card({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card">
      <div className="card__header">
        <div>
          <h3>{title}</h3>
          {subtitle && <p className="card__subtitle">{subtitle}</p>}
        </div>
        {right && <div className="card__right">{right}</div>}
      </div>
      <div className="card__body">{children}</div>
    </section>
  );
}
