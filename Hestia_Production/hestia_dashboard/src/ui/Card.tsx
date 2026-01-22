import React from "react";
import "./Card.css";

export type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
};

export function Card({
  title,
  subtitle,
  actions,
  footer,
  className = "",
  children,
  ...props
}: CardProps) {
  return (
    <div className={`uiCard ${className}`} {...props}>
      {(title || subtitle || actions) && (
        <div className="uiCard__head">
          <div className="uiCard__titles">
            {title && <div className="uiCard__title">{title}</div>}
            {subtitle && <div className="uiCard__subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="uiCard__actions">{actions}</div>}
        </div>
      )}
      <div className="uiCard__body">{children}</div>
      {footer && <div className="uiCard__footer">{footer}</div>}
    </div>
  );
}
