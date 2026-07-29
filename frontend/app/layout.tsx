import "./globals.css";
import type { ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import { Flame, Activity, ShieldAlert, Cpu, Users, Landmark } from "lucide-react";

import { AuthProvider } from "@/components/AuthProvider";
import UserNav from "@/components/UserNav";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono" });

export const metadata = {
  title: "Pricing the Heat -- AI Climate Micro-Insurance Platform",
  description:
    "Parametric heat-wage-loss insurance for informal outdoor workers, priced per state from " +
    "each state's own real climate regime -- income smoothing or catastrophe cover, powered by STGCN GNNs.",
};

const NAV_LINKS = [
  { href: "/", label: "Heat Map & Live Data", icon: Flame },
  { href: "/simulate", label: "Policy Simulator", icon: Activity },
  { href: "/admin", label: "Manager Dashboard", icon: Users },
  { href: "/insurance", label: "Insurance Provider", icon: Landmark },
  { href: "/methodology", label: "Methodology & Models", icon: Cpu },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-[#FAFAFA] text-slate-900 font-sans antialiased selection:bg-orange-100 selection:text-orange-900">
        <AuthProvider>
          {/* Top Floating Header */}
          <header className="sticky top-0 z-50 glass-header">
            <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3 px-4 sm:px-6 py-3.5">
              
              {/* Brand Logo */}
              <Link href="/" className="group flex items-center gap-2.5 transition-transform active:scale-95">
                <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-tr from-amber-500 via-orange-500 to-red-500 text-white shadow-md shadow-orange-500/20 group-hover:scale-105 transition-transform duration-300">
                  <Flame className="w-5 h-5 fill-white/20 animate-pulse-glow" />
                  <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400"></span>
                  </span>
                </div>
                <div>
                  <span className="font-bold text-lg tracking-tight text-slate-900 group-hover:text-orange-600 transition-colors">
                    Pricing the Heat
                  </span>
                  <span className="block text-[10px] uppercase font-semibold tracking-wider text-orange-600/90 -mt-1">
                    Climate Micro-Insurance AI
                  </span>
                </div>
              </Link>

              {/* Navigation Links */}
              <nav className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-full border border-slate-200/80 shadow-inner">
                {NAV_LINKS.map((l) => {
                  const Icon = l.icon;
                  return (
                    <Link
                      key={l.href}
                      href={l.href}
                      className="flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold text-slate-600 hover:text-slate-900 hover:bg-white hover:shadow-xs transition-all duration-200"
                    >
                      <Icon className="w-3.5 h-3.5 text-orange-500" />
                      <span>{l.label}</span>
                    </Link>
                  );
                })}
              </nav>

              {/* Auth Status / UserNav & Live Status Badge */}
              <div className="flex items-center gap-3">
                <UserNav />
                
                <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200/60 text-emerald-800 text-xs font-medium">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <span className="font-mono font-semibold">79 STATES</span>
                </div>
              </div>

            </div>
          </header>

          {/* Main Content Viewport */}
          {children}
        </AuthProvider>

        {/* Footer */}
        <footer className="mt-20 border-t border-slate-200/80 bg-white py-10 text-xs text-slate-500">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-orange-500" />
              <span>Parametric Heat Wage Insurance &copy; {new Date().getFullYear()} Pricing the Heat</span>
            </div>
            <div className="flex gap-6 font-mono text-slate-400">
              <span>NASA POWER API</span>
              <span>STGCN Neural Net</span>
              <span>Wang Copula Transformer</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
