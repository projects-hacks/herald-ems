// A hand-drawn SVG sparkline (no chart library, no animation: docs/API_CONTRACT.md).
export function Sparkline({ values, width = 120, height = 32, label, className = "text-text-secondary" }: {
  values: number[]; width?: number; height?: number; label: string; className?: string;
}) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * (width - 4) + 2},${height - 2 - ((v - lo) / span) * (height - 4)}`);
  const [lx, ly] = pts[pts.length - 1].split(",");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} className={className}>
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth={2} strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r={3} fill="currentColor" />
    </svg>
  );
}
