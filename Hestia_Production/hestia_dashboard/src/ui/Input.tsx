import React from "react";
import "./Input.css";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
};

export function Input({ label, hint, error, className = "", id, ...props }: InputProps) {
  const autoId = React.useId();
  const inputId = id ?? `input-${autoId}`;
  const describedBy = error
    ? `${inputId}-error`
    : hint
      ? `${inputId}-hint`
      : undefined;

  return (
    <div className={`uiField ${className}`.trim()}>
      {label ? (
        <label className="uiField__label" htmlFor={inputId}>
          {label}
        </label>
      ) : null}

      <input
        id={inputId}
        className={`uiInput ${error ? "uiInput--error" : ""}`.trim()}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        {...props}
      />

      {error ? (
        <div id={`${inputId}-error`} className="uiField__msg uiField__msg--error">
          {error}
        </div>
      ) : hint ? (
        <div id={`${inputId}-hint`} className="uiField__msg">
          {hint}
        </div>
      ) : null}
    </div>
  );
}
