import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from "recharts";
import { SimulatePolicyResponse } from "@/lib/types";

export function PremiumBarChart({ result, windowDays }: { result: SimulatePolicyResponse, windowDays: number }) {
  if (!result.wage_provenance || !result.premium_lsmc || !result.premium_wang) return null;

  const totalWage = result.wage_provenance.value * windowDays;
  
  const data = [
    {
      name: "Total Window Wage",
      Amount: totalWage,
      fill: "#10b981", // emerald-500
    },
    {
      name: "Pure Premium",
      Amount: result.premium_lsmc,
      fill: "#64748b", // slate-500
    },
    {
      name: "Loaded Premium",
      Amount: result.premium_wang,
      fill: "#f97316", // orange-500
    },
  ];

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 11, fontWeight: "bold", fill: "#64748b" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: "#64748b" }} axisLine={false} tickLine={false} tickFormatter={(val) => `${result.currency} ${val}`} />
          <Tooltip 
            cursor={{ fill: "#f8fafc" }}
            contentStyle={{ borderRadius: "8px", border: "1px solid #e2e8f0", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }}
            formatter={(val: number) => [`${result.currency} ${val.toFixed(2)}`, 'Amount']}
          />
          <Bar dataKey="Amount" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
