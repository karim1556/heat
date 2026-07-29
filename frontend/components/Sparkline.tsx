type Props = { points: Array<{ ts: string; mu_tevi: number }> };

const WIDTH = 320;
const HEIGHT = 56;

export function Sparkline({ points }: Props) {
  if (points.length === 0) return null;

  const values = points.map((p) => p.mu_tevi);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const pts = points.map((p, i) => {
    const x = (i / (points.length - 1 || 1)) * WIDTH;
    const y = HEIGHT - 8 - ((p.mu_tevi - min) / range) * (HEIGHT - 16);
    return [x, y] as [number, number];
  });

  const path = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const areaPath = `${path} L ${WIDTH} ${HEIGHT} L 0 ${HEIGHT} Z`;

  return (
    <div className="relative rounded-xl bg-slate-50/80 p-2 border border-slate-200/80">
      <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="mu-TEVI index series">
        <defs>
          <linearGradient id="sparklineGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#ff5722" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#sparklineGrad)" />
        <path d={path} fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {pts.length > 0 && (
          <circle
            cx={pts[pts.length - 1][0]}
            cy={pts[pts.length - 1][1]}
            r={3.5}
            fill="#d97706"
            stroke="#ffffff"
            strokeWidth={1.5}
          />
        )}
      </svg>
    </div>
  );
}
