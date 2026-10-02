"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { sameDraft, type Draft, type Parsed } from "@/lib/saisies";

type LoadState = "loading" | "error" | "ready";

/** Lecture et enregistrement d'une grille ; fonctions définies au niveau du module (stables). */
export type GridApi<T, I> = {
  load: (companyId: number, jour: string) => Promise<T>;
  save: (companyId: number, jour: string, input: I) => Promise<T>;
  toDraft: (data: T) => Draft;
};

/**
 * État d'une grille saisie à la main pour une société et une date : chargement, brouillon des
 * cellules, cellules invalides et enregistrement.
 */
export function useSaisieGrid<T, I>(companyId: number, jour: string, api: GridApi<T, I>) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [saved, setSaved] = useState<Draft>({});
  const [draft, setDraft] = useState<Draft>({});
  const [invalid, setInvalid] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.load(companyId, jour).then(
      (data) => {
        if (cancelled) return;
        const loaded = api.toDraft(data);
        setSaved(loaded);
        setDraft(loaded);
        setInvalid([]);
        setError(null);
        setLoadState("ready");
      },
      () => {
        if (!cancelled) setLoadState("error");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, companyId, jour, reloadKey]);

  function setCell(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
    setInvalid((current) => (current.includes(key) ? current.filter((k) => k !== key) : current));
  }

  function reset() {
    setDraft(saved);
    setInvalid([]);
    setError(null);
  }

  function retry() {
    setLoadState("loading");
    setReloadKey((key) => key + 1);
  }

  /** Enregistre la grille ; retourne vrai si c'est fait. */
  async function submit(parsed: Parsed<I>): Promise<boolean> {
    if (!parsed.ok) {
      setInvalid(parsed.invalid);
      setError(null);
      return false;
    }
    setSaving(true);
    setError(null);
    try {
      const stored = api.toDraft(await api.save(companyId, jour, parsed.value));
      setSaved(stored);
      setDraft(stored);
      setInvalid([]);
      return true;
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Une erreur est survenue.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  return {
    loadState,
    draft,
    setCell,
    invalid,
    dirty: !sameDraft(saved, draft),
    saving,
    error,
    reset,
    retry,
    submit,
  };
}
