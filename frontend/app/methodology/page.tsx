import fs from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import {
  Cpu,
  Flame,
  Activity,
  Layers,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Database,
  Search,
} from "lucide-react";

export const metadata = {
  title: "Methodology & Models -- Pricing the Heat",
};

const STATEWISE_MD_PATH = path.join(process.cwd(), "..", "docs", "STATEWISE_RESULTS.md");

type MdTable = { headers: string[]; rows: string[][] };

function splitRow(line: string): string[] {
  const trimmed = line.trim();
  const inner = trimmed.startsWith("|") && trimmed.endsWith("|") ? trimmed.slice(1, -1) : trimmed;
  return inner.split("|").map((cell) => cell.trim());
}

function extractTables(markdown: string): MdTable[] {
  const lines = markdown.split("\n");
  const tables: MdTable[] = [];
  let block: string[] = [];
  for (const line of lines) {
    if (line.trim().startsWith("|")) {
      block.push(line);
    } else if (block.length > 0) {
      if (block.length >= 2) tables.push({ headers: splitRow(block[0]), rows: block.slice(2).map(splitRow) });
      block = [];
    }
  }
  if (block.length >= 2) tables.push({ headers: splitRow(block[0]), rows: block.slice(2).map(splitRow) });
  return tables;
}

function renderInlineMd(text: string): ReactNode {
  const parts: ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(
        <strong key={key++} className="font-bold text-slate-900">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      parts.push(
        <code key={key++} className="text-[11px] font-mono bg-slate-100 text-amber-800 px-1.5 py-0.5 rounded border border-slate-200">
          {token.slice(1, -1)}
        </code>,
      );
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

function MdTableView({ table }: { table: MdTable }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-sm">
      <div className="overflow-x-auto max-h-[500px]">
        <table className="min-w-full text-xs text-left">
          <thead className="sticky top-0 z-10 bg-slate-100/90 backdrop-blur-md border-b border-slate-200 text-slate-700 font-bold uppercase tracking-wider">
            <tr>
              {table.headers.map((h, i) => (
                <th key={i} className="px-4 py-3 whitespace-nowrap">
                  {renderInlineMd(h)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {table.rows.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50/80 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className="px-4 py-2.5 whitespace-nowrap text-slate-800 font-medium">
                    {renderInlineMd(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MethodologyPage() {
  let statewiseMd: string | null = null;
  let loadError: string | null = null;
  try {
    statewiseMd = fs.readFileSync(STATEWISE_MD_PATH, "utf-8");
  } catch {
    loadError = "Could not load docs/STATEWISE_RESULTS.md at build time -- no results table displayed.";
  }

  const tables = statewiseMd ? extractTables(statewiseMd) : [];
  const pricedTable = tables[0] ?? null;
  const excludedTable = tables[1] ?? null;
  const generatedMatch = statewiseMd?.match(/_Generated ([^_]+)_/);
  const gridCeilingMatch = statewiseMd?.match(/\*\*Grid-ceiling audit\*\*: (.+)/);

  return (
    <main className="max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-10">
      
      {/* Header Banner */}
      <div className="space-y-3 border-b border-slate-200/80 pb-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-50 border border-orange-200 text-xs font-bold uppercase tracking-wider text-orange-800">
          <Cpu className="w-3.5 h-3.5 text-orange-500" />
          <span>Parametric Modeling Architecture</span>
        </div>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">How Pricing the Heat Works</h1>
        <p className="text-sm text-slate-600 leading-relaxed max-w-3xl">
          <strong>Pricing the Heat</strong> is a parametric micro-insurance product for informal outdoor workers across 79 Indian and US states, priced from each state's own real weather, wages, and climate regime.
        </p>
      </div>

      {/* Methodology Section 1: Heat Source */}
      <section className="glass-card p-6 rounded-2xl space-y-3 border border-slate-200/80 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500 text-white font-bold flex items-center justify-center text-xs">
            01
          </div>
          <h2 className="text-base font-bold text-slate-900">Where the Heat Comes From (STGCN Neural Net)</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed pl-11">
          A spatio-temporal graph convolutional network (STGCN) forecasts street-level heat (shade-WBGT) at every weather grid cell from NASA POWER's public API. The model is trained on each state's ~2° anchor-metro grid, ensuring laptop-trainable efficiency across 79 states. The map displays inductively forecasted heat surfaces across the entire state border.
        </p>
      </section>

      {/* Methodology Section 2: Wage Loss Model */}
      <section className="glass-card p-6 rounded-2xl space-y-3 border border-slate-200/80 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-orange-500 text-white font-bold flex items-center justify-center text-xs">
            02
          </div>
          <h2 className="text-base font-bold text-slate-900">How Wage Loss is Modeled (Multi-Agent POMDP)</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed pl-11">
          A behavioral simulation of individual workers (multi-agent POMDP trained with reinforcement learning) models how workers trade off income against thermal strain. Elasticity parameters follow published occupational heat literature (~2.6% wage loss per degree above threshold for vendors; ~0.57%/degree for construction). Baseline wages cite each state's official minimum-wage schedule.
        </p>
      </section>

      {/* Methodology Section 3: Copula Index */}
      <section className="glass-card p-6 rounded-2xl space-y-3 border border-slate-200/80 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-red-500 text-white font-bold flex items-center justify-center text-xs">
            03
          </div>
          <h2 className="text-base font-bold text-slate-900">Fusing Heat & Loss into the mu-TEVI Index</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed pl-11">
          A Gumbel survival copula fuses each state's heat trigger with modeled worker wage loss into the single <strong>mu-TEVI index (0-100)</strong>. Because parametric policies payout on an index rather than indemnity claim verification, basis risk (shortfall/overpay probability) is calculated and disclosed transparently on every quote.
        </p>
      </section>

      {/* Methodology Section 4: Contract Pricing */}
      <section className="glass-card p-6 rounded-2xl space-y-3 border border-slate-200/80 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-slate-900 text-white font-bold flex items-center justify-center text-xs">
            04
          </div>
          <h2 className="text-base font-bold text-slate-900">Pricing the Contract (LSMC & Wang Transform)</h2>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed pl-11">
          A Longstaff-Schwartz Monte Carlo (LSMC) option pricer evaluates each state's policy from its fitted joint distribution. A Wang transform then loads an insurer's risk margin onto the fair actuarial price.
        </p>
      </section>

      {/* Methodology Section 5: State-Wise Results Table */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <h2 className="text-xl font-bold text-slate-900">State-wise Calibrated Contracts</h2>
            {generatedMatch && <p className="text-xs text-slate-500">Generated: {generatedMatch[1]}</p>}
          </div>
          <div className="text-xs font-mono text-slate-500 bg-slate-100 px-3 py-1 rounded-full border border-slate-200">
            Real 10-Year Historical Replay
          </div>
        </div>

        {loadError && (
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs">
            {loadError}
          </div>
        )}

        {pricedTable && <MdTableView table={pricedTable} />}

        {gridCeilingMatch && (
          <p className="text-xs text-slate-500 font-mono italic">{gridCeilingMatch[1]}</p>
        )}
      </section>

      {/* Methodology Section 6: Excluded States */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-slate-900">Excluded States Audit</h2>
        <p className="text-xs text-slate-600">
          States with insufficient extreme heat exposure days are documented and excluded rather than forced with synthetic data.
        </p>
        {excludedTable && <MdTableView table={excludedTable} />}
      </section>

      {/* Methodology Section 7: Data Provenance */}
      <section className="glass-card p-6 rounded-2xl space-y-4 border border-slate-200/80 shadow-sm">
        <div className="flex items-center gap-2 font-bold text-slate-900 text-base">
          <Database className="w-5 h-5 text-orange-500" />
          <span>Data Provenance & Audit Trail</span>
        </div>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-700">
          <li className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
            <span className="font-bold text-slate-900">Heat Source:</span> NASA POWER Regional API (real fetches with provenance sidecars).
          </li>
          <li className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
            <span className="font-bold text-slate-900">Labor Structure:</span> World Bank Indicators API v2.
          </li>
          <li className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
            <span className="font-bold text-slate-900">Minimum Wage:</span> State labor department public schedules.
          </li>
          <li className="bg-slate-50 p-3 rounded-xl border border-slate-200/80">
            <span className="font-bold text-slate-900">Elasticity:</span> Cited occupational heat stress literature.
          </li>
        </ul>
      </section>

    </main>
  );
}
