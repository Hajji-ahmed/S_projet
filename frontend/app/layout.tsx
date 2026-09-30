import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "SIMTIS Finance", template: "%s · SIMTIS Finance" },
  description: "Plateforme de trésorerie et de rapprochement bancaire",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" className={inter.variable}>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
