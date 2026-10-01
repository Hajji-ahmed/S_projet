export const DEFAULT_PATH = "/dashboard";
export const LOGIN_PATH = "/login";

/**
 * Chemin où revenir après la connexion (`/login?next=...`). Seuls les chemins INTERNES sont suivis :
 * une adresse comme `//site.com` ou `https://site.com` pourrait envoyer l'utilisateur sur un faux site.
 */
export function safeNextPath(next: string | null | undefined, fallback = DEFAULT_PATH): string {
  if (!next) return fallback;
  const isInternal =
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.includes("\\") &&
    // Caractères de contrôle (retour à la ligne, tabulation...) : jamais dans un chemin légitime
    ![...next].some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127);
  if (!isInternal) return fallback;
  if (
    next === LOGIN_PATH ||
    next.startsWith(`${LOGIN_PATH}?`) ||
    next.startsWith(`${LOGIN_PATH}/`)
  ) {
    return fallback;
  }
  return next;
}

export function loginPathFor(currentPath: string): string {
  const next = safeNextPath(currentPath, "");
  return next ? `${LOGIN_PATH}?next=${encodeURIComponent(next)}` : LOGIN_PATH;
}
