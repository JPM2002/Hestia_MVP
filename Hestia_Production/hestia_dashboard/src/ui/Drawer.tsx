import React from "react";
import "./Drawer.css";

export type DrawerProps = {
  open: boolean;
  title?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: number; // px
};

export function Drawer({ open, title, onClose, children, footer, width = 420 }: DrawerProps) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="uiDrawerOverlay" onMouseDown={onClose}>
      <div
        className="uiDrawer"
        style={{ width }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="uiDrawer__head">
          <div className="uiDrawer__title">{title ?? ""}</div>
          <button className="uiDrawer__close" onClick={onClose} aria-label="Cerrar">
            ✕
          </button>
        </div>
        <div className="uiDrawer__body">{children}</div>
        {footer ? <div className="uiDrawer__footer">{footer}</div> : null}
      </div>
    </div>
  );
}
