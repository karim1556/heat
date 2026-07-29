type Props = {
  strike: number;
  cap: number;
  samplePoints: Record<string, number>;
};

const WIDTH = 340;
const HEIGHT = 160;
const PAD = 28;

function payoutFraction(index: number, strike: number, cap: number): number {
  const frac = (index - strike) / (100 - strike);
  return cap * Math.min(Math.max(frac, 0), 1);
}

export function PayoutChart({ strike, cap, samplePoints }: Props) {
  const points: Array<[number, number]> = [];
  for (let idx = 0; idx <= 100; idx += 2) {
    points.push([idx, payoutFraction(idx, strike, cap)]);
  }

  const xScale = (idx: number) => PAD + (idx / 100) * (WIDTH - 2 * PAD);
  const yScale = (frac: number) => HEIGHT - PAD - (frac / cap) * (HEIGHT - 2 * PAD);

  const path = points
    .map(([idx, frac], i) => `${i === 0 ? "M" : "L"} ${xScale(idx).toFixed(1)} ${yScale(frac).toFixed(1)}`)
    .join(" ");

  const areaPath = `${path} L ${xScale(100).toFixed(1)} ${HEIGHT - PAD} L ${xScale(0).toFixed(1)} ${HEIGHT - PAD} Z`;

  return (
    <div className="relative rounded-2xl bg-gradient-to-b from-slate-50 to-white p-3 border border-slate-200/80 shadow-sm">
      <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Payout schedule chart">
        <defs>
          <linearGradient id="payoutGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff5722" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        <line x1={PAD} y1={HEIGHT - PAD} x2={WIDTH - PAD} y2={HEIGHT - PAD} stroke="#e2e8f0" strokeWidth="1.5" />
        <line x1={PAD} y1={PAD} x2={PAD} y2={HEIGHT - PAD} stroke="#e2e8f0" strokeWidth="1.5" />

        {/* Strike threshold marker */}
        <line
          x1={xScale(strike)}
          y1={PAD - 5}
          x2={xScale(strike)}
          y2={HEIGHT - PAD}
          stroke="#dc2626"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />

        {/* Area under curve */}
        <path d={areaPath} fill="url(#payoutGradient)" />

        {/* Payout curve */}
        <path d={path} fill="none" stroke="#ff5722" strokeWidth="2.5" strokeLinecap="round" />

        {/* Sample Points */}
        {Object.entries(samplePoints).map(([idxStr, frac]) => (
          <circle
            key={idxStr}
            cx={xScale(Number(idxStr))}
            cy={yScale(frac)}
            r={4}
            fill="#dc2626"
            stroke="#ffffff"
            strokeWidth={1.5}
            className="shadow-sm"
          />
        ))}

        {/* Axis Labels */}
        <text x={PAD} y={HEIGHT - 8} fontSize={10} fontFamily="var(--font-jetbrains-mono)" fill="#64748b">
          0
        </text>
        <text x={WIDTH - PAD - 18} y={HEIGHT - 8} fontSize={10} fontFamily="var(--font-jetbrains-mono)" fill="#64748b">
          100
        </text>
        
        {/* Strike Label Badge */}
        <text x={Math.min(xScale(strike) + 4, WIDTH - 80)} y={PAD + 6} fontSize={10} fontWeight="600" fill="#dc2626" fontFamily="var(--font-jetbrains-mono)">
          Strike: {strike}
        </text>
      </svg>
    </div>
  );
}
