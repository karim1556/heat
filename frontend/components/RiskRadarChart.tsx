import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from "recharts";
import { SimulatePolicyResponse } from "@/lib/types";

export function RiskRadarChart({ result }: { result: SimulatePolicyResponse }) {
  if (!result.basis_risk) return null;

  const data = [
    {
      subject: "Trigger Accuracy",
      A: Math.round((1 - result.basis_risk.shortfall_rate) * 100),
      fullMark: 100,
    },
    {
      subject: "Shortfall Risk",
      A: Math.round(result.basis_risk.shortfall_rate * 100),
      fullMark: 100,
    },
    {
      subject: "Overpay Risk",
      A: Math.round(result.basis_risk.overpay_rate * 100),
      fullMark: 100,
    },
  ];

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: "#64748b", fontSize: 11, fontWeight: "bold" }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 10 }} />
          <Tooltip 
            contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }}
            formatter={(val: number) => [`${val}%`, '']}
          />
          <Radar name="Risk Metrics" dataKey="A" stroke="#f59e0b" fill="#fbbf24" fillOpacity={0.5} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
