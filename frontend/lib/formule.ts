import { amountForInput } from "@/lib/accounts";

/**
 * Formules des cellules de montant (tableau Prévisions, 30/10/2026) : « =1 200,50+350*2 » devient
 * « 1 900,50 » quand on appuie sur Entrée ou quitte la cellule. Seul le résultat est gardé.
 * Opérations + − * / et parenthèses, calcul exact (fractions en BigInt, jamais de float), résultat
 * arrondi au centime, 0,005 vers le haut. Le texte est lu par un petit analyseur : rien n'est exécuté.
 */

type Fraction = { n: bigint; d: bigint };

// Pas de littéraux « 0n » : la cible TypeScript est antérieure à ES2020 (comme statementLines.ts)
const ZERO = BigInt(0);
const UN = BigInt(1);
const DEUX = BigInt(2);
const CENT = BigInt(100);

/** Le texte commence par « = » : c'est une formule. */
export function estFormule(texte: string): boolean {
  return texte.trim().startsWith("=");
}

/** « =1200+350,50 » → « 1 550,50 » ; formule fausse ou division par zéro → null. */
export function evaluerFormule(texte: string): string | null {
  const corps = texte
    .trim()
    .replace(/^=/, "")
    // Espaces (milliers, insécables) ignorés ; signe moins typographique d'un copier-coller
    .replace(/[\s  ]/g, "")
    .replace(/[−‑–]/g, "-")
    .replace(/[×]/g, "*")
    .replace(/[÷]/g, "/");
  if (!corps) return null;
  const lecteur = new Lecteur(corps);
  let valeur: Fraction | null;
  try {
    valeur = lecteur.expression();
  } catch {
    return null; // texte collé démesuré (pile d'appels dépassée)
  }
  if (valeur === null || !lecteur.fini()) return null;
  return amountForInput(centimes(valeur));
}

/** Fraction → « -1550.50 », arrondie au centime (moitié vers le haut, en valeur absolue). */
function centimes({ n, d }: Fraction): string {
  const negatif = n < ZERO !== d < ZERO;
  const num = (n < ZERO ? -n : n) * CENT;
  const den = d < ZERO ? -d : d;
  let cents = num / den;
  if ((num % den) * DEUX >= den) cents += UN;
  const entier = cents / CENT;
  const reste = (cents % CENT).toString().padStart(2, "0");
  return `${negatif && cents > ZERO ? "-" : ""}${entier}.${reste}`;
}

function pgcd(a: bigint, b: bigint): bigint {
  a = a < ZERO ? -a : a;
  b = b < ZERO ? -b : b;
  while (b) [a, b] = [b, a % b];
  return a;
}

function reduite(n: bigint, d: bigint): Fraction {
  const g = pgcd(n, d) || UN;
  return d < ZERO ? { n: -n / g, d: -d / g } : { n: n / g, d: d / g };
}

const PROFONDEUR_MAX = 50;

class Lecteur {
  private pos = 0;
  private profondeur = 0;

  constructor(private readonly texte: string) {}

  fini(): boolean {
    return this.pos === this.texte.length;
  }

  private voir(): string {
    return this.texte[this.pos] ?? "";
  }

  // expression := terme (('+' | '-') terme)*
  expression(): Fraction | null {
    let gauche = this.terme();
    while (gauche && (this.voir() === "+" || this.voir() === "-")) {
      const op = this.texte[this.pos++];
      const droite = this.terme();
      if (!droite) return null;
      gauche =
        op === "+"
          ? reduite(gauche.n * droite.d + droite.n * gauche.d, gauche.d * droite.d)
          : reduite(gauche.n * droite.d - droite.n * gauche.d, gauche.d * droite.d);
    }
    return gauche;
  }

  // terme := facteur (('*' | '/') facteur)*
  private terme(): Fraction | null {
    let gauche = this.facteur();
    while (gauche && (this.voir() === "*" || this.voir() === "/")) {
      const op = this.texte[this.pos++];
      const droite = this.facteur();
      if (!droite) return null;
      if (op === "/" && droite.n === ZERO) return null;
      gauche =
        op === "*"
          ? reduite(gauche.n * droite.n, gauche.d * droite.d)
          : reduite(gauche.n * droite.d, gauche.d * droite.n);
    }
    return gauche;
  }

  // facteur := ('-' | '+') facteur | '(' expression ')' | nombre
  private facteur(): Fraction | null {
    const c = this.voir();
    if (c === "-" || c === "+") {
      this.pos++;
      const valeur = this.facteur();
      return valeur && c === "-" ? { n: -valeur.n, d: valeur.d } : valeur;
    }
    if (c === "(") {
      if (++this.profondeur > PROFONDEUR_MAX) return null;
      this.pos++;
      const valeur = this.expression();
      if (!valeur || this.voir() !== ")") return null;
      this.pos++;
      this.profondeur--;
      return valeur;
    }
    return this.nombre();
  }

  // nombre := chiffres ((',' | '.') chiffres)?
  private nombre(): Fraction | null {
    const lu = /^(\d+)(?:[.,](\d+))?/.exec(this.texte.slice(this.pos));
    if (!lu) return null;
    this.pos += lu[0].length;
    const decimales = lu[2] ?? "";
    return reduite(BigInt(lu[1] + decimales), BigInt(`1${"0".repeat(decimales.length)}`));
  }
}
