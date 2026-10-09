import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Racine explicite : évite qu'un package-lock.json d'un dossier parent soit pris pour la racine du projet.
  turbopack: { root: process.cwd() },
  // Accès depuis le réseau local en développement (téléphone, autre PC) : adresses déclarées dans
  // ALLOWED_DEV_ORIGINS (.env). Vide par défaut.
  allowedDevOrigins: (process.env.ALLOWED_DEV_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
};

export default nextConfig;
