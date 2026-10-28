"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fusionnerLignes, resteALire } from "@/lib/reconciliation";

type Lu<P, T> = {
  cle: string;
  /** Première page : ses compteurs (par statut, à comptabiliser…) valent pour tout le filtre. */
  premiere: P;
  lignes: T[];
  total: number;
  pages: number;
};

/**
 * Volets du rapprochement sans boutons Suivant (28/10/2026) : les pages de 50 lignes s'ajoutent
 * quand on approche du bas. `cle` décrit le filtre : la changer repart de la première page ;
 * `recharge` relit les pages déjà affichées sans revenir en haut (après un rapprochement).
 */
export function useDefilement<P, T extends { id: number }>(
  cle: string,
  recharge: string,
  lire: (page: number) => Promise<P>,
  extraire: (page: P) => { total: number; lignes: T[] },
) {
  const [lu, setLu] = useState<Lu<P, T> | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [suite, setSuite] = useState(false);
  const luRef = useRef<Lu<P, T> | null>(null);
  const suiteRef = useRef(false);
  const lireRef = useRef(lire);
  const extraireRef = useRef(extraire);
  useEffect(() => {
    lireRef.current = lire;
    extraireRef.current = extraire;
  });

  useEffect(() => {
    let annule = false;
    // Même filtre : on relit autant de pages qu'affichées, pour garder la position
    const nombre = luRef.current?.cle === cle ? luRef.current.pages : 1;
    Promise.all(Array.from({ length: nombre }, (_, i) => lireRef.current(i + 1))).then(
      (pages) => {
        if (annule) return;
        const lues = pages.map((page) => extraireRef.current(page));
        const resultat: Lu<P, T> = {
          cle,
          premiere: pages[0],
          lignes: lues.reduce<T[]>((lignes, page) => fusionnerLignes(lignes, page.lignes), []),
          total: lues[lues.length - 1].total,
          pages: nombre,
        };
        luRef.current = resultat;
        setLu(resultat);
      },
      () => {
        if (!annule) setErreur(`${cle}|${recharge}`);
      },
    );
    return () => {
      annule = true;
    };
  }, [cle, recharge]);

  const chargerPlus = useCallback(() => {
    const actuel = luRef.current;
    if (!actuel || actuel.cle !== cle || suiteRef.current) return;
    if (!resteALire(actuel.lignes.length, actuel.total)) return;
    suiteRef.current = true;
    setSuite(true);
    lireRef
      .current(actuel.pages + 1)
      .then(
        (page) => {
          // Un rechargement est passé entre-temps : sa lecture fait foi
          if (luRef.current !== actuel) return;
          const lue = extraireRef.current(page);
          const suivant: Lu<P, T> = {
            ...actuel,
            lignes: fusionnerLignes(actuel.lignes, lue.lignes),
            total: lue.total,
            pages: actuel.pages + 1,
          };
          luRef.current = suivant;
          setLu(suivant);
        },
        () => undefined,
      )
      .finally(() => {
        suiteRef.current = false;
        setSuite(false);
      });
  }, [cle]);

  const pret = lu !== null && lu.cle === cle;
  const etat: "loading" | "error" | "ready" =
    erreur === `${cle}|${recharge}` ? "error" : pret ? "ready" : "loading";
  return {
    etat,
    lu: pret ? lu : null,
    /** Dernières lignes lues, même d'un ancien filtre : le tableau (et ses filtres d'en-tête) reste
     * affiché, grisé, pendant qu'un nouveau filtre se charge (28/10/2026). */
    affiche: lu,
    suite,
    reste: pret ? resteALire(lu.lignes.length, lu.total) : false,
    chargerPlus,
  };
}
