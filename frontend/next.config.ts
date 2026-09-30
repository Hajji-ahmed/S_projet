import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Racine explicite : évite qu'un package-lock.json d'un dossier parent soit pris pour la racine du projet.
  turbopack: { root: process.cwd() },
};

export default nextConfig;
