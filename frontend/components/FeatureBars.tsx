type Props = { contributions: Record<string, number> };

export function FeatureBars({ contributions }: Props) {
  const entries = Object.entries(contributions).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-3">
      {entries.map(([name, value]) => {
        const pct = (value * 100).toFixed(1);
        const widthVal = Math.min(Math.max(value * 100, 2), 100);

        return (
          <div key={name} className="text-xs">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-slate-700 capitalize">
                {name.replace(/_/g, " ")}
              </span>
              <span className="font-mono font-bold text-orange-600 bg-orange-50 px-2 py-0.5 rounded border border-orange-200/60">
                {pct}%
              </span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden p-0.5 border border-slate-200/60">
              <div
                className="bg-gradient-to-r from-amber-500 to-orange-500 h-full rounded-full transition-all duration-500 shadow-sm"
                style={{ width: `${widthVal}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
