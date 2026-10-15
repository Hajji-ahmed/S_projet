"use client";

import { FileSpreadsheet, SlidersHorizontal, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { NumberInput } from "@/components/ui/Field";
import { LoadingState } from "@/components/ui/LoadingState";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import { brouillonDe, reglesModifiees } from "@/lib/parametres";
import { formatDateTime } from "@/lib/statements";
import { deleteMapping, getGrille, getMappings, saveGrille } from "@/services/parametres";
import type { ModeleMapping, Regle, RegleInput } from "@/types/parametres";

const SECTIONS: [Regle["genre"], string, string][] = [
  [
    "critere",
    "Critères du score",
    "Points apportés par chaque critère ; le total est plafonné à 100.",
  ],
  [
    "fenetre",
    "Fenêtre de comparaison",
    "Seules les écritures à ± N jours d'une opération sont comparées.",
  ],
  [
    "seuil",
    "Seuils",
    "Score minimal d'une proposition, d'une forte correspondance, et écart d'une concurrente proche.",
  ],
];

/** Paramètres (P16.3) : grille du rapprochement et modèles de mapping d'import. */
export function ParametresTab() {
  return (
    <div className="space-y-6">
      <GrilleCard />
      <MappingsCard />
    </div>
  );
}

function GrilleCard() {
  const { toast } = useToast();
  const [regles, setRegles] = useState<Regle[] | null>(null);
  const [brouillon, setBrouillon] = useState<RegleInput[]>([]);
  const [erreur, setErreur] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [version, setVersion] = useState(0);
  const recharger = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    let annule = false;
    getGrille().then(
      (r) => {
        if (annule) return;
        setRegles(r);
        setBrouillon(brouillonDe(r));
        setErreur(false);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [version]);

  const modifiees = useMemo(
    () => (regles ? reglesModifiees(regles, brouillon) : []),
    [regles, brouillon],
  );

  function changer(code: string, champ: keyof RegleInput, valeur: string | boolean) {
    setBrouillon((liste) => liste.map((r) => (r.code === code ? { ...r, [champ]: valeur } : r)));
  }

  async function enregistrer() {
    setEnvoi(true);
    try {
      const resultat = await saveGrille(modifiees);
      setRegles(resultat);
      setBrouillon(brouillonDe(resultat));
      toast("Grille enregistrée : elle vaut pour le prochain lancement du rapprochement.");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Enregistrement impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Card title="Grille de rapprochement" icon={SlidersHorizontal}>
      <p className="mb-4 max-w-3xl text-sm text-simtis-muted">
        Une modification vaut pour le prochain lancement du moteur ; les propositions en attente
        gardent leur score jusqu&apos;à la relance. Une proposition reste toujours validée par un
        humain.
      </p>
      {erreur ? (
        <ErrorState message="Impossible de charger la grille." onRetry={recharger} />
      ) : regles === null ? (
        <LoadingState rows={6} />
      ) : (
        <div className="space-y-5">
          {SECTIONS.map(([genre, titre, aide]) => {
            const lignes = regles.filter((r) => r.genre === genre);
            if (lignes.length === 0) return null;
            return (
              <section key={genre}>
                <h3 className="text-sm font-semibold text-simtis-text">{titre}</h3>
                <p className="mb-2 text-xs text-simtis-muted">{aide}</p>
                <div className="divide-y divide-simtis-border rounded-[14px] border border-simtis-border">
                  {lignes.map((regle) => {
                    const valeur = brouillon.find((r) => r.code === regle.code);
                    if (!valeur) return null;
                    return (
                      <div
                        key={regle.code}
                        className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3"
                      >
                        <div className="min-w-[220px] flex-1">
                          <p className="text-sm font-medium text-simtis-text">{regle.libelle}</p>
                          <p className="font-mono text-[11px] text-simtis-muted">
                            {regle.code} · modifié le {formatDateTime(regle.updated_at)}
                          </p>
                        </div>
                        {genre !== "fenetre" && (
                          <label className="flex items-center gap-2 text-sm text-simtis-muted">
                            <NumberInput
                              aria-label={`Points : ${regle.libelle}`}
                              className="h-9 w-24"
                              inputMode="decimal"
                              value={valeur.poids}
                              disabled={genre === "critere" && !valeur.actif}
                              onChange={(e) => changer(regle.code, "poids", e.target.value)}
                            />
                            points
                          </label>
                        )}
                        {(genre === "fenetre" || regle.code === "DATE") && (
                          <label className="flex items-center gap-2 text-sm text-simtis-muted">
                            {regle.code === "DATE" && "tolérance"}
                            <NumberInput
                              aria-label={`Jours : ${regle.libelle}`}
                              className="h-9 w-20"
                              inputMode="numeric"
                              value={valeur.tolerance ?? ""}
                              disabled={genre === "critere" && !valeur.actif}
                              onChange={(e) => changer(regle.code, "tolerance", e.target.value)}
                            />
                            jours
                          </label>
                        )}
                        {genre === "critere" && (
                          <label className="flex cursor-pointer items-center gap-2 text-sm text-simtis-text">
                            <input
                              type="checkbox"
                              checked={valeur.actif}
                              onChange={(e) => changer(regle.code, "actif", e.target.checked)}
                              className="h-4 w-4 accent-simtis-primary"
                            />
                            Actif
                          </label>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
          <div className="flex flex-wrap items-center justify-end gap-2">
            {modifiees.length > 0 && (
              <span className="mr-auto text-sm text-simtis-muted">
                {modifiees.length} paramètre{modifiees.length > 1 ? "s" : ""} modifié
                {modifiees.length > 1 ? "s" : ""}
              </span>
            )}
            <Button
              variant="secondary"
              onClick={() => setBrouillon(brouillonDe(regles))}
              disabled={envoi || modifiees.length === 0}
            >
              Annuler
            </Button>
            <Button onClick={enregistrer} disabled={envoi || modifiees.length === 0}>
              {envoi ? "Enregistrement..." : "Enregistrer la grille"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function MappingsCard() {
  const { toast } = useToast();
  const [mappings, setMappings] = useState<ModeleMapping[] | null>(null);
  const [erreur, setErreur] = useState(false);
  const [suppression, setSuppression] = useState<ModeleMapping | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [version, setVersion] = useState(0);
  const recharger = useCallback(() => setVersion((n) => n + 1), []);

  useEffect(() => {
    let annule = false;
    getMappings().then(
      (m) => {
        if (annule) return;
        setMappings(m);
        setErreur(false);
      },
      () => {
        if (!annule) setErreur(true);
      },
    );
    return () => {
      annule = true;
    };
  }, [version]);

  async function supprimer() {
    if (!suppression) return;
    setEnvoi(true);
    try {
      await deleteMapping(suppression.id);
      toast("Modèle supprimé : le prochain import refera la détection des colonnes.");
      setSuppression(null);
      recharger();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Suppression impossible.", "error");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Card title="Modèles de mapping d'import" icon={FileSpreadsheet}>
      <p className="mb-4 max-w-3xl text-sm text-simtis-muted">
        SIMTIS mémorise les colonnes de chaque banque (relevés) et de chaque société (Sage) à la
        confirmation d&apos;un import. Supprimer un modèle force la détection au prochain import.
      </p>
      {erreur ? (
        <ErrorState message="Impossible de charger les modèles." onRetry={recharger} />
      ) : mappings === null ? (
        <LoadingState rows={3} />
      ) : mappings.length === 0 ? (
        <p className="text-sm text-simtis-muted">Aucun modèle mémorisé.</p>
      ) : (
        <ul className="divide-y divide-simtis-border rounded-[14px] border border-simtis-border">
          {mappings.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="rounded-full bg-simtis-light px-2 py-0.5 text-xs font-medium text-simtis-primary-dark">
                {m.type === "Banque" ? "Relevé" : "Sage"}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-simtis-text">
                  {m.banque ? `${m.banque} · ` : ""}
                  {m.nom}
                </span>
                <span className="block truncate text-xs text-simtis-muted">
                  {Object.keys(m.mapping).length} champs · modifié le {formatDateTime(m.updated_at)}
                </span>
              </span>
              <button
                type="button"
                onClick={() => setSuppression(m)}
                title="Supprimer"
                aria-label={`Supprimer le modèle ${m.nom}`}
                className="rounded-[10px] p-2 text-simtis-muted transition-colors hover:bg-simtis-danger-bg hover:text-simtis-danger-fg"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {suppression && (
        <Modal
          open
          title="Supprimer ce modèle ?"
          onClose={() => !envoi && setSuppression(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setSuppression(null)} disabled={envoi}>
                Annuler
              </Button>
              <Button variant="danger" onClick={supprimer} disabled={envoi}>
                {envoi ? "Suppression..." : "Supprimer"}
              </Button>
            </>
          }
        >
          <p>
            Le modèle <strong>{suppression.nom}</strong> sera oublié. Le prochain import refera la
            détection des colonnes et le mémorisera de nouveau à la confirmation.
          </p>
        </Modal>
      )}
    </Card>
  );
}
