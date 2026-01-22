import React from "react";
import "./Skeleton.css";

export type SkeletonProps = {
  width?: string | number;
  height?: string | number;
  style?: React.CSSProperties;
  className?: string;
};

export function Skeleton({ width = "100%", height = 14, style, className = "" }: SkeletonProps) {
  const w = typeof width === "number" ? `${width}px` : width;
  const h = typeof height === "number" ? `${height}px` : height;
  return <div className={`uiSkeleton ${className}`} style={{ width: w, height: h, ...style }} />;
}
