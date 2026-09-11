import "./globals.css";
import type { ReactNode } from "react";
import { DM_Sans, Space_Grotesk, JetBrains_Mono } from "next/font/google";

import { AuthProvider } from "@/components/AuthProvider";
import { AppShell } from "@/components/AppShell";

const dmSans = DM_Sans({ subsets: ["latin"], variable: "--font-dm-sans" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono" });

export const metadata = {
  title: "Pricing the Heat -- AI Climate Micro-Insurance Platform",
  description:
    "Parametric heat-wage-loss insurance for informal outdoor workers, priced per state from " +
    "each state's own real climate regime -- income smoothing or catastrophe cover, powered by STGCN GNNs.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${dmSans.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
