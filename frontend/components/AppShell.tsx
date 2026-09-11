import type { ReactNode } from "react";
import Link from "next/link";
import { Activity, Cpu, Flame, Landmark, Users } from "lucide-react";
import UserNav from "@/components/UserNav";

const navigation = [
  { href: "/", label: "Heat Map & Live Data", icon: Flame },
  { href: "/simulate", label: "Policy Simulator", icon: Activity },
  { href: "/admin", label: "Manager Dashboard", icon: Users },
  { href: "/insurance", label: "Insurance Provider", icon: Landmark },
  { href: "/methodology", label: "Methodology & Models", icon: Cpu },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="obs-shell" data-testid="app-shell" data-theme="auto">
      <header className="obs-header"><div className="obs-header-inner">
        <Link href="/" className="obs-brand" aria-label="Pricing the Heat home"><span className="obs-brand-mark"><Flame aria-hidden="true" /></span><span><strong>Pricing the Heat</strong><small>Climate risk observatory</small></span></Link>
        <nav className="obs-nav" aria-label="Primary navigation">{navigation.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className="obs-nav-link"><Icon aria-hidden="true" /><span>{label}</span></Link>)}</nav>
        <div className="obs-account"><UserNav /></div>
      </div></header>
      <main className="obs-main">{children}</main>
      <footer className="obs-footer"><span>Parametric Heat Wage Insurance © {new Date().getFullYear()} Pricing the Heat</span><span>NASA POWER · State-calibrated pricing · Basis risk disclosed</span></footer>
    </div>
  );
}
