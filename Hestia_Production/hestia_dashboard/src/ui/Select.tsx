import React from "react";
import "./Select.css";

export type SelectOption = { value: string; label: string; disabled?: boolean };

export type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  hint?: string;
  error?: string;
  options?: SelectOption[];
};

export function Select({
  label,
  hint,
  error,
  className = "",
  id,
  options,
  children,
  ...props
}: SelectProps) {
  const autoId = React.useId();
  const selectId = id ?? `select-${autoId}`;
  const describedBy = error
    ? `${selectId}-error`
    : hint
      ? `${selectId}-hint`
      : undefined;

  return (
    <div className="uiField">
      {label && (
        <label className="uiField__label" htmlFor={selectId}>
          {label}
        </label>
      )}

      <div className="uiSelectWrap">
        <select
          id={selectId}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={`uiSelect ${error ? "uiSelect--error" : ""} ${className}`}
          {...props}
        >
          {options
            ? options.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </option>
              ))
            : children}
        </select>
        <span className="uiSelectChevron" aria-hidden>
          ▾
        </span>
      </div>

      {error ? (
        <div id={`${selectId}-error`} className="uiField__msg uiField__msg--error">
          {error}
        </div>
      ) : hint ? (
        <div id={`${selectId}-hint`} className="uiField__msg">
          {hint}
        </div>
      ) : null}
    </div>
  );
}
