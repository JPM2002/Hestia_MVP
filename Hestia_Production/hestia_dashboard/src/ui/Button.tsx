import React from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
};

function cx(...parts: Array<string | false | undefined | null>) {
  return parts.filter(Boolean).join(" ");
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  leftIcon,
  rightIcon,
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = Boolean(disabled || loading);

  return (
    <button
      className={cx("uiBtn", `uiBtn--${variant}`, `uiBtn--${size}`, className)}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="uiBtn__spinner" aria-hidden="true" /> : leftIcon}
      <span className="uiBtn__label">{children}</span>
      {rightIcon ? <span className="uiBtn__right">{rightIcon}</span> : null}
    </button>
  );
}
